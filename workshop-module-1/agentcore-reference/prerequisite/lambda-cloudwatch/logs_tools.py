"""CloudWatch Logs tools for CAN server."""

import asyncio
import boto3  # type: ignore
import datetime
import os
import json
from aws_lambda_powertools import Logger  # type: ignore
from botocore.config import Config  # type: ignore
from mcp.server.fastmcp import Context
from pydantic import Field
from timeit import default_timer as timer
from typing import Annotated, Dict, List, Literal, Optional, Any

from amzn_astro_mcp_server.utils.decorators import DecoratorManager
from amzn_astro_mcp_server.utils.helper_functions import assumed_role_session
from amzn_astro_mcp_server.servers.can.cloudwatch.models import (
    LogAnomaly,
    LogAnomalyDetector,
    LogAnomalyResults,
    LogGroupMetadata,
    LogsAnalysisResult,
    LogsMetadata,
    LogsQueryCancelResult,
    SavedLogsInsightsQuery,
)
from amzn_astro_mcp_server.servers.can.cloudwatch.utils import (
    clean_up_pattern,
    filter_by_prefixes,
    remove_null_values,
)

# Get logger
logger = Logger(service="astro_mcp_server")

# Version for user agent
CW_TOOLS_VERSION = "1.0.0"


class CloudWatchLogsTools:
    """CloudWatch Logs tools implementation for CAN server."""

    def __init__(self):
        """Initialize the CloudWatch Logs tools."""
        self._logs_client = None
        self._logs_client_region = None

    @property
    def logs_client(self):
        """Get the logs client for the default region (us-east-1)."""
        if self._logs_client is None or self._logs_client_region != 'us-east-1':
            self._logs_client = self._get_logs_client('us-east-1')
            self._logs_client_region = 'us-east-1'
        return self._logs_client

    def _get_logs_client(self, region: str):
        """Create a CloudWatch Logs client for the specified region."""
        config = Config(user_agent_extra=f'awslabs/mcp/cloudwatch-mcp-server/{CW_TOOLS_VERSION}')

        try:
            if aws_profile := os.environ.get('AWS_PROFILE'):
                return boto3.Session(profile_name=aws_profile, region_name=region).client(
                    'logs', config=config
                )
            else:
                return boto3.Session(region_name=region).client('logs', config=config)
        except Exception as e:
            logger.error(f'Error creating cloudwatch logs client for region {region}: {str(e)}')
            raise

    def _validate_log_group_parameters(
        self, log_group_names: Optional[List[str]], log_group_identifiers: Optional[List[str]]
    ) -> None:
        """Validate that exactly one of log_group_names or log_group_identifiers is provided.

        Args:
            log_group_names: List of log group names
            log_group_identifiers: List of log group identifiers

        Raises:
            ValueError: If both or neither parameters are provided
        """
        if bool(log_group_names) == bool(log_group_identifiers):
            raise ValueError(
                'Exactly one of log_group_names or log_group_identifiers must be provided'
            )

    def _convert_time_to_timestamp(self, time_str: str) -> int:
        """Convert ISO 8601 time string to Unix timestamp.

        Args:
            time_str: ISO 8601 formatted time string

        Returns:
            Unix timestamp as integer
        """
        return int(datetime.datetime.fromisoformat(time_str).timestamp())

    def _build_logs_query_params(
        self,
        log_group_names: Optional[List[str]],
        log_group_identifiers: Optional[List[str]],
        start_time: str,
        end_time: str,
        query_string: str,
        limit: Optional[int],
    ) -> Dict[str, Any]:  # Fixed return type to Dict[str, Any] instead of just Dict
        """Build parameters for CloudWatch Logs Insights query."""
        return {
            'startTime': self._convert_time_to_timestamp(start_time),
            'endTime': self._convert_time_to_timestamp(end_time),
            'queryString': query_string,
            'logGroupIdentifiers': log_group_identifiers,
            'logGroupNames': log_group_names,
            'limit': limit,
        }

    def _process_query_results(self, response: Dict, query_id: str = '') -> Dict:
        """Process query results response into standardized format."""
        return {
            'queryId': query_id or response.get('queryId', ''),
            'status': response['status'],
            'statistics': response.get('statistics', {}),
            'results': [
                {field['field']: field['value'] for field in line}
                for line in response.get('results', [])
            ],
        }

    async def _poll_for_query_completion(
        self, logs_client, query_id: str, max_timeout: int, ctx: Context
    ) -> Dict:
        """Poll for query completion within the specified timeout."""
        poll_start = timer()
        while poll_start + max_timeout > timer():
            response = logs_client.get_query_results(queryId=query_id)
            status = response['status']

            if status in {'Complete', 'Failed', 'Cancelled'}:
                logger.info(f'Query {query_id} finished with status {status}')
                return self._process_query_results(response, query_id)

            await asyncio.sleep(1)

        msg = f'Query {query_id} did not complete within {max_timeout} seconds. Use get_logs_insight_query_results with the returned queryId to try again to retrieve query results.'
        logger.warning(msg)
        await ctx.warning(msg)
        return {
            'queryId': query_id,
            'status': 'Polling Timeout',
            'message': msg,
        }

    def register(self, mcp):
        """Register all CloudWatch Logs tools with the MCP server."""
        # Register describe_log_groups tool
        mcp.tool(
            name='describe_log_groups',
            description="Lists AWS CloudWatch log groups and saved queries associated with them, optionally filtering by a name prefix."
        )(self.describe_log_groups)

        # Register analyze_log_group tool
        mcp.tool(
            name='analyze_log_group',
            description="Analyzes a CloudWatch log group for anomalies, message patterns, and error patterns within a specified time window."
        )(self.analyze_log_group)

        # Register execute_log_insights_query tool
        mcp.tool(
            name='execute_log_insights_query',
            description="Executes a CloudWatch Logs Insights query and waits for the results to be available."
        )(self.execute_log_insights_query)

        # Register get_logs_insight_query_results tool
        mcp.tool(
            name='get_logs_insight_query_results',
            description="Retrieves the results of a previously started CloudWatch Logs Insights query."
        )(self.get_logs_insight_query_results)

        # Register cancel_logs_insight_query tool
        mcp.tool(
            name='cancel_logs_insight_query',
            description="Cancels an ongoing CloudWatch Logs Insights query. If the query has already ended, returns an error that the given query is not running."
        )(self.cancel_logs_insight_query)

    @DecoratorManager.exception_handler()
    async def describe_log_groups(
        self,
        ctx: Context,
        account_identifiers: Annotated[
            List[str] | None,
            Field(
                description=(
                    'When include_linked_accounts is set to True, use this parameter to specify the list of accounts to search. IMPORTANT: Only has affect if include_linked_accounts is True'
                )
            ),
        ] = None,
        include_linked_accounts: Annotated[
            bool | None,
            Field(
                description=(
                    """If the AWS account is a monitoring account, set this to True to have the tool return log groups in the accounts listed in account_identifiers.
                If this parameter is set to true and account_identifiers contains a null value, the tool returns all log groups in the monitoring account and all log groups in all source accounts that are linked to the monitoring account."""
                )
            ),
        ] = False,
        log_group_class: Annotated[
            Literal['STANDARD', 'INFREQUENT_ACCESS'] | None,
            Field(
                description=('If specified, filters for only log groups of the specified class.')
            ),
        ] = None,
        log_group_name_prefix: Annotated[
            str | None,
            Field(
                description=(
                    'An exact prefix to filter log groups by name. IMPORTANT: Only log groups with names starting with this prefix will be returned.'
                )
            ),
        ] = None,
        max_items: Annotated[
            int | None, Field(description=('The maximum number of log groups to return.'))
        ] = None,
        region: Annotated[
            str,
            Field(description='AWS region to query. Defaults to us-east-1.'),
        ] = 'us-east-1',
    ) -> LogsMetadata:
        """Lists AWS CloudWatch log groups and saved queries associated with them, optionally filtering by a name prefix."""
        # Create logs client for the specified region
        logs_client = self._get_logs_client(region)

        def describe_log_groups() -> List[LogGroupMetadata]:
            nonlocal max_items  # Tell Python this is the outer function's variable
            if max_items is not None:
                try:
                    max_items = int(max_items)
                except (ValueError, TypeError):
                    # If conversion fails, use a reasonable default
                    logger.warning(f"Invalid max_items value: {max_items}, using default of 50")
                    max_items = 50
            paginator = logs_client.get_paginator('describe_log_groups')
            kwargs = {
                'accountIdentifiers': account_identifiers,
                'includeLinkedAccounts': include_linked_accounts,
                'logGroupNamePrefix': log_group_name_prefix,
                'logGroupClass': log_group_class,
            }
            
            # Remove null values from kwargs
            cleaned_kwargs = remove_null_values(kwargs)
            
            # Create pagination config separately
            pagination_config = {'MaxItems': max_items} if max_items else None
            
            # Pass pagination_config as a separate parameter
            log_groups = []
            for page in paginator.paginate(**cleaned_kwargs, PaginationConfig=pagination_config):
                log_groups.extend(page.get('logGroups', []))
            
            logger.info(f'Log groups: {log_groups}')
            return [LogGroupMetadata.model_validate(lg) for lg in log_groups]

            
        def get_filtered_saved_queries(
            log_groups: List[LogGroupMetadata],
        ) -> List[SavedLogsInsightsQuery]:
            saved_queries = []
            next_token = None
            first_iteration = True

            # No paginator for this API
            while first_iteration or next_token:
                first_iteration = False
                # TODO: Support other query language types
                kwargs = {'nextToken': next_token, 'queryLanguage': 'CWLI'}
                response = logs_client.describe_query_definitions(**remove_null_values(kwargs))
                saved_queries.extend(response.get('queryDefinitions', []))

                next_token = response.get('nextToken')

            logger.info(f'Saved queries: {saved_queries}')
            modeled_queries = [
                SavedLogsInsightsQuery.model_validate(saved_query) for saved_query in saved_queries
            ]

            log_group_targets = {lg.logGroupName for lg in log_groups}
            # filter to only saved queries applicable to log groups we're looking at
            return [
                query
                for query in modeled_queries
                if (query.logGroupNames & log_group_targets)
                or filter_by_prefixes(log_group_targets, query.logGroupPrefixes)
            ]

        try:
            log_groups = describe_log_groups()
            filtered_saved_queries = get_filtered_saved_queries(log_groups)
            return LogsMetadata(
                log_group_metadata=log_groups, saved_queries=filtered_saved_queries
            )

        except Exception as e:
            logger.error(f'Error in describe_log_groups_tool: {str(e)}')
            await ctx.error(f'Error in describing log groups: {str(e)}')
            raise

    @DecoratorManager.exception_handler()
    async def analyze_log_group(
        self,
        ctx: Context,
        log_group_arn: str = Field(
            ...,
            description='The log group arn to look for anomalies in, as returned by the describe_log_groups tools',
        ),
        start_time: str = Field(
            ...,
            description=(
                'ISO 8601 formatted start time for the CloudWatch Logs Insights query window (e.g., "2025-04-19T20:00:00+00:00").'
            ),
        ),
        end_time: str = Field(
            ...,
            description=(
                'ISO 8601 formatted end time for the CloudWatch Logs Insights query window (e.g., "2025-04-19T21:00:00+00:00").'
            ),
        ),
        region: Annotated[
            str,
            Field(description='AWS region to query. Defaults to us-east-1.'),
        ] = 'us-east-1',
    ) -> LogsAnalysisResult:
        """Analyzes a CloudWatch log group for anomalies, message patterns, and error patterns within a specified time window."""
        def is_applicable_anomaly(anomaly: LogAnomaly) -> bool:
            # Must have overlap - convert to datetime objects for proper comparison
            try:
                anomaly_first_seen = datetime.datetime.fromisoformat(anomaly.firstSeen)
                anomaly_last_seen = datetime.datetime.fromisoformat(anomaly.lastSeen)
                end_time_dt = datetime.datetime.fromisoformat(end_time)
                start_time_dt = datetime.datetime.fromisoformat(start_time)

                if anomaly_first_seen > end_time_dt or anomaly_last_seen < start_time_dt:
                    return False
            except ValueError as e:
                logger.error(f'Error parsing timestamps for anomaly comparison: {e}')
                # Fall back to string comparison if datetime parsing fails
                if anomaly.firstSeen > end_time or anomaly.lastSeen < start_time:
                    return False

            # Must be for this log group
            return log_group_arn in anomaly.logGroupArnList

        # Create logs client for the specified region
        logs_client = self._get_logs_client(region)

        async def get_applicable_anomalies() -> LogAnomalyResults:
            detectors: List[LogAnomalyDetector] = []
            paginator = logs_client.get_paginator('list_log_anomaly_detectors')
            for page in paginator.paginate(filterLogGroupArn=log_group_arn):
                detectors.extend(
                    [
                        LogAnomalyDetector.model_validate(d)
                        for d in page.get('anomalyDetectors', [])
                    ]
                )

            logger.info(f'Found {len(detectors)} anomaly detectors for log group')

            # 2 & 3. Get and filter anomalies for each detector
            anomalies: List[LogAnomaly] = []
            for detector in detectors:
                paginator = logs_client.get_paginator('list_anomalies')

                for page in paginator.paginate(
                    anomalyDetectorArn=detector.anomalyDetectorArn, suppressionState='UNSUPPRESSED'
                ):
                    anomalies.extend(
                        LogAnomaly.model_validate(anomaly) for anomaly in page.get('anomalies', [])
                    )

            applicable_anomalies = [
                anomaly for anomaly in anomalies if is_applicable_anomaly(anomaly)
            ]
            logger.info(
                f'Found {len(anomalies)} anomaly detectors for log group, {len(applicable_anomalies)} of which are applicable'
            )

            return LogAnomalyResults(anomaly_detectors=detectors, anomalies=applicable_anomalies)

        try:
            # 1. Get anomaly detectors for this log group
            log_anomaly_results, pattern_query_result, error_pattern_result = await asyncio.gather(
                get_applicable_anomalies(),
                self.execute_log_insights_query(
                    ctx,
                    log_group_names=None,
                    log_group_identifiers=[log_group_arn],
                    start_time=start_time,
                    end_time=end_time,
                    query_string='pattern @message | sort @sampleCount desc | limit 5',
                    limit=5,
                    max_timeout=30,
                ),
                self.execute_log_insights_query(
                    ctx,
                    log_group_names=None,
                    log_group_identifiers=[log_group_arn],
                    start_time=start_time,
                    end_time=end_time,
                    query_string='fields @timestamp, @message | filter @message like /(?i)(error|exception|fail|timeout|fatal)/ | pattern @message | limit 5',
                    limit=5,
                    max_timeout=30,
                ),
            )

            clean_up_pattern(pattern_query_result.get('results', []))
            clean_up_pattern(error_pattern_result.get('results', []))

            return LogsAnalysisResult(
                log_anomaly_results=log_anomaly_results,
                top_patterns=pattern_query_result,
                top_patterns_containing_errors=error_pattern_result,
            )

        except Exception as e:
            logger.error(f'Error in analyze_log_group_tool: {str(e)}')
            await ctx.error(f'Error analyzing log group: {str(e)}')
            raise

    @DecoratorManager.exception_handler()
    async def execute_log_insights_query(
        self,
        ctx: Context,
        log_group_names: Annotated[
            List[str] | None,
            Field(
                max_length=50,
                description='The list of up to 50 log group names to be queried. CRITICAL: Exactly one of [log_group_names, log_group_identifiers] should be non-null.',
            ),
        ] = None,
        log_group_identifiers: Annotated[
            List[str] | None,
            Field(
                max_length=50,
                description="The list of up to 50 logGroupIdentifiers to query. You can specify them by the log group name or ARN. If a log group that you're querying is in a source account and you're using a monitoring account, you must use the ARN. CRITICAL: Exactly one of [log_group_names, log_group_identifiers] should be non-null.",
            ),
        ] = None,
        start_time: str = Field(
            ...,
            description=(
                'ISO 8601 formatted start time for the CloudWatch Logs Insights query window (e.g., "2025-04-19T20:00:00+00:00").'
            ),
        ),
        end_time: str = Field(
            ...,
            description=(
                'ISO 8601 formatted end time for the CloudWatch Logs Insights query window (e.g., "2025-04-19T21:00:00+00:00").'
            ),
        ),
        query_string: str = Field(
            ...,
            description='The query string in the Cloudwatch Log Insights Query Language. See https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html.',
        ),
        limit: Annotated[
            int | None,
            Field(
                description='The maximum number of log events to return. It is critical to use either this parameter or a `| limit <int>` operator in the query to avoid consuming too many tokens of the agent.'
            ),
        ] = None,
        max_timeout: Annotated[
            int,
            Field(
                description='Maximum time in second to poll for complete results before giving up'
            ),
        ] = 30,
        region: Annotated[
            str,
            Field(description='AWS region to query. Defaults to us-east-1.'),
        ] = 'us-east-1',
    ) -> Dict:
        """Executes a CloudWatch Logs Insights query and waits for the results to be available."""
        try:
            # Validate parameters
            self._validate_log_group_parameters(log_group_names, log_group_identifiers)

            # Build query parameters
            kwargs = self._build_logs_query_params(
                log_group_names, log_group_identifiers, start_time, end_time, query_string, limit
            )

            # Create logs client for the specified region
            logs_client = self._get_logs_client(region)

            # Start the query
            start_response = logs_client.start_query(**remove_null_values(kwargs))
            query_id = start_response['queryId']
            logger.info(f'Started query with ID: {query_id}')

            # Poll for completion
            return await self._poll_for_query_completion(logs_client, query_id, max_timeout, ctx)

        except Exception as e:
            logger.error(f'Error in execute_log_insights_query_tool: {str(e)}')
            await ctx.error(f'Error executing CloudWatch Logs Insights query: {str(e)}')
            raise

    @DecoratorManager.exception_handler()
    async def get_logs_insight_query_results(
        self,
        ctx: Context,
        query_id: str = Field(
            ...,
            description='The unique ID of the query to retrieve the results for. CRITICAL: This ID is returned by the execute_log_insights_query tool.',
        ),
        region: Annotated[
            str,
            Field(description='AWS region to query. Defaults to us-east-1.'),
        ] = 'us-east-1',
    ) -> Dict:
        """Retrieves the results of a previously started CloudWatch Logs Insights query."""
        try:
            # Create logs client for the specified region
            logs_client = self._get_logs_client(region)

            response = logs_client.get_query_results(queryId=query_id)

            logger.info(f'Retrieved results for query ID {query_id}')

            return self._process_query_results(response, query_id)
        except Exception as e:
            logger.error(f'Error in get_query_results_tool: {str(e)}')
            await ctx.error(f'Error retrieving CloudWatch Logs Insights query results: {str(e)}')
            raise

    @DecoratorManager.exception_handler()
    async def cancel_logs_insight_query(
        self,
        ctx: Context,
        query_id: str = Field(
            ...,
            description='The unique ID of the ongoing query to cancel. CRITICAL: This ID is returned by the execute_log_insights_query tool.',
        ),
        region: Annotated[
            str,
            Field(description='AWS region to query. Defaults to us-east-1.'),
        ] = 'us-east-1',
    ) -> LogsQueryCancelResult:
        """Cancels an ongoing CloudWatch Logs Insights query. If the query has already ended, returns an error that the given query is not running."""
        try:
            # Create logs client for the specified region
            logs_client = self._get_logs_client(region)

            response = logs_client.stop_query(queryId=query_id)
            return LogsQueryCancelResult.model_validate(response)
        except Exception as e:
            logger.error(f'Error in cancel_query_tool: {str(e)}')
            await ctx.error(f'Error cancelling CloudWatch Logs Insights query: {str(e)}')
            raise
