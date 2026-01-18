"""CloudWatch Metrics tools for CAN server."""

import boto3
import json
import os
from datetime import datetime
from pathlib import Path
from aws_lambda_powertools import Logger
from botocore.config import Config
from mcp.server.fastmcp import Context
from pydantic import Field
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from amzn_astro_mcp_server.utils.decorators import DecoratorManager
from amzn_astro_mcp_server.servers.can.cloudwatch.models import (
    AlarmRecommendation,
    AlarmRecommendationDimension,
    AlarmRecommendationThreshold,
    Dimension,
    GetMetricDataResponse,
    MetricDataPoint,
    MetricDataResult,
    MetricMetadata,
    MetricMetadataIndexKey,
)
from amzn_astro_mcp_server.servers.can.cloudwatch.utils import remove_null_values

# Get logger
logger = Logger(service="astro_mcp_server")

# Version for user agent
CW_TOOLS_VERSION = "1.0.0"


class CloudWatchMetricsTools:
    """CloudWatch Metrics tools implementation for CAN server."""

    def __init__(self):
        """Initialize the CloudWatch Metrics tools."""
        # Load and index metric metadata
        self.metric_metadata_index: Dict[MetricMetadataIndexKey, Any] = (
            self._load_and_index_metadata()
        )
        logger.info(f'Loaded {len(self.metric_metadata_index)} metric metadata entries')

    def _get_cloudwatch_client(self, region: str):
        """Create a CloudWatch client for the specified region."""
        config = Config(user_agent_extra=f'amzn_astro_mcp_server/cloudwatch-tools/{CW_TOOLS_VERSION}')

        try:
            if aws_profile := os.environ.get('AWS_PROFILE'):
                return boto3.Session(profile_name=aws_profile, region_name=region).client(
                    'cloudwatch', config=config
                )
            else:
                return boto3.Session(region_name=region).client('cloudwatch', config=config)
        except Exception as e:
            logger.error(f'Error creating cloudwatch client for region {region}: {str(e)}')
            raise

    def _load_and_index_metadata(self) -> Dict[MetricMetadataIndexKey, Any]:
        """Load metric metadata from JSON file and create an indexed structure."""
        try:
            # Get the path to the metadata file
            current_dir = Path(__file__).parent
            metadata_dir = current_dir / 'data'
            
            # Create directory if it doesn't exist
            metadata_dir.mkdir(exist_ok=True)
            
            metadata_file = metadata_dir / 'metric_metadata.json'

            # Create an empty metadata file if it doesn't exist
            if not metadata_file.exists():
                logger.warning(f'Metric metadata file not found: {metadata_file}')
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump([], f)
                return {}

            # Load the JSON data
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata_list = json.load(f)

            logger.info(f'Loaded {len(metadata_list)} metric metadata entries')

            # Create the indexed structure
            index = {}

            for entry in metadata_list:
                try:
                    metric_id = entry.get('metricId', {})
                    namespace = metric_id.get('namespace')
                    metric_name = metric_id.get('metricName')

                    if not namespace or not metric_name:
                        continue

                    # Create the index key (no dimensions)
                    key = MetricMetadataIndexKey(namespace=namespace, metric_name=metric_name)

                    # Store the entry
                    index[key] = entry

                except Exception as e:
                    logger.warning(f'Error processing metadata entry: {e}')
                    continue

            logger.info(f'Successfully indexed {len(index)} metric metadata entries')
            return index

        except Exception as e:
            logger.error(f'Error loading metric metadata: {e}')
            return {}

    def _lookup_metadata(self, namespace: str, metric_name: str) -> Dict[str, Any]:
        """Look up metadata for a specific metric."""
        key = MetricMetadataIndexKey(namespace=namespace, metric_name=metric_name)
        return self.metric_metadata_index.get(key, {})

    def register(self, mcp):
        """Register all CloudWatch Metrics tools with the MCP server."""
        # Register get_metric_data tool
        mcp.tool(
            name='get_metric_data',
            description="Retrieves CloudWatch metric data for a specific metric."
        )(self.get_metric_data)

        # Register get_metric_metadata tool
        mcp.tool(
            name='get_metric_metadata',
            description="Gets metadata for a CloudWatch metric including description, unit and recommended statistics that can be used for metric data retrieval."
        )(self.get_metric_metadata)

        # Register get_recommended_metric_alarms tool
        mcp.tool(
            name='get_recommended_metric_alarms',
            description="Gets recommended alarms for a CloudWatch metric."
        )(self.get_recommended_metric_alarms)

    @DecoratorManager.exception_handler()
    async def get_metric_data(
        self,
        ctx: Context,
        namespace: str,
        metric_name: str,
        start_time: Union[str, datetime],
        dimensions: List[Dimension] = [],
        end_time: Annotated[
            Union[str, datetime] | None,
            Field(
                description='The end time for the metric data query (ISO format or datetime), defaults to current time'
            ),
        ] = None,
        statistic: Annotated[
            Literal[
                'AVG',
                'COUNT',
                'MAX',
                'MIN',
                'SUM',
                'Average',
                'Sum',
                'Maximum',
                'Minimum',
                'SampleCount',
            ],
            Field(description='The statistic to use for the metric'),
        ] = 'AVG',
        target_datapoints: Annotated[
            int,
            Field(
                description='Target number of data points to return (default: 60). Controls the granularity of the returned data.'
            ),
        ] = 60,
        group_by_dimension: Annotated[
            str | None,
            Field(
                description='Dimension name to group by in Metrics Insights mode. Must be included in schema_dimension_keys.'
            ),
        ] = None,
        schema_dimension_keys: Annotated[
            List[str],
            Field(
                description='List of dimension keys to include in the SCHEMA definition for Metrics Insights query.'
            ),
        ] = [],
        limit: Annotated[
            int | None,
            Field(
                description='Maximum number of results to return in Metrics Insights mode (used with LIMIT clause).'
            ),
        ] = None,
        sort_order: Annotated[
            Literal['ASC', 'DESC'] | None,
            Field(
                description="Sort order for results when using ORDER BY in Metrics Insights. Can be 'ASC', 'DESC', or None."
            ),
        ] = None,
        order_by_statistic: Annotated[
            Literal['AVG', 'COUNT', 'MAX', 'MIN', 'SUM'] | None,
            Field(
                description='Statistic to use in the ORDER BY clause. Required if sort_order is specified.'
            ),
        ] = None,
        region: Annotated[
            str,
            Field(description='AWS region to query. Defaults to us-east-1.'),
        ] = 'us-east-1',
    ) -> GetMetricDataResponse:
        """Retrieves CloudWatch metric data for a specific metric."""
        try:
            # Process time parameters and calculate period
            start_time, end_time, period = self._prepare_time_parameters(
                start_time, end_time, target_datapoints
            )

            # Determine which query method to use and build the appropriate query
            use_metrics_insights = any(
                [
                    group_by_dimension is not None,
                    schema_dimension_keys,
                    limit is not None,
                    sort_order is not None,
                    order_by_statistic is not None,
                ]
            )

            if use_metrics_insights:
                metric_query = self._build_metrics_insights_query(
                    namespace,
                    metric_name,
                    dimensions,
                    statistic,
                    period,
                    group_by_dimension,
                    schema_dimension_keys,
                    order_by_statistic,
                    sort_order,
                    limit,
                )
            else:
                metric_query = self._build_standard_metric_query(
                    namespace, metric_name, dimensions, statistic, period
                )

            # Create CloudWatch client for the specified region
            cloudwatch_client = self._get_cloudwatch_client(region)

            # Call the GetMetricData API
            response = cloudwatch_client.get_metric_data(
                MetricDataQueries=[metric_query], StartTime=start_time, EndTime=end_time
            )

            # Process the response
            return self._process_metric_data_response(response)

        except Exception as e:
            logger.error(f'Error in get_metric_data: {str(e)}')
            await ctx.error(f'Error getting metric data: {str(e)}')
            raise

    def _prepare_time_parameters(self, start_time, end_time, target_datapoints):
        """Process time parameters and calculate the period."""
        # Convert string times to datetime objects
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))

        if end_time is None:
            end_time = datetime.utcnow()
        elif isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))

        # Calculate period based on time window and target datapoints
        time_window_seconds = int((end_time - start_time).total_seconds())
        calculated_period = max(60, int(time_window_seconds / target_datapoints))

        # Round up to the nearest multiple of 60
        period = (
            calculated_period + (60 - calculated_period % 60)
            if calculated_period % 60 != 0
            else calculated_period
        )

        logger.info(
            f'Calculated period: {period} seconds for time window of {time_window_seconds} seconds with target of {target_datapoints} datapoints'
        )

        return start_time, end_time, period

    def _build_metrics_insights_query(
        self,
        namespace,
        metric_name,
        dimensions,
        statistic,
        period,
        group_by_dimension,
        schema_dimension_keys,
        order_by_statistic,
        sort_order,
        limit,
    ):
        """Build a Metrics Insights query."""
        logger.info(f'Building Metrics Insights query for {namespace}/{metric_name}')

        # Validate that group_by_dimension is included in schema_dimension_keys
        if group_by_dimension is not None and group_by_dimension not in schema_dimension_keys:
            raise ValueError(
                f"group_by_dimension '{group_by_dimension}' must be included in schema_dimension_keys: {schema_dimension_keys}"
            )

        # Check if sort_order is specified but order_by_statistic is not
        if sort_order is not None and order_by_statistic is None:
            raise ValueError(
                'If sort_order is specified, order_by_statistic must also be specified'
            )

        # Map and validate statistics
        metrics_insights_statistic = self._map_to_metrics_insights_statistic(statistic)

        # Build the query components
        query_parts = []

        # SELECT clause
        query_parts.append(f'SELECT {metrics_insights_statistic}("{metric_name}")')

        # FROM clause with SCHEMA
        schema_str = self._build_schema_string(namespace, schema_dimension_keys)
        query_parts.append(f'FROM SCHEMA({schema_str})')

        # WHERE clause for dimensions
        if dimensions:
            where_clause = self._build_where_clause(dimensions)
            if where_clause:
                query_parts.append(where_clause)

        # GROUP BY clause
        if group_by_dimension:
            query_parts.append(f'GROUP BY "{group_by_dimension}"')

        # ORDER BY clause
        if order_by_statistic is not None:
            order_by_stat = order_by_statistic.upper()
            self._validate_metrics_insights_statistic(order_by_stat)

            order_clause = f'ORDER BY {order_by_stat}()'
            if sort_order is not None:
                order_clause += f' {sort_order}'

            query_parts.append(order_clause)

        # LIMIT clause
        if limit is not None and limit > 0:
            query_parts.append(f'LIMIT {limit}')

        # Join all parts to form the complete query
        query = ' '.join(query_parts)
        logger.info(f'Built Metrics Insights query: {query}')

        return {'Id': 'm1', 'Expression': query, 'Period': period, 'ReturnData': True}

    def _build_standard_metric_query(self, namespace, metric_name, dimensions, statistic, period):
        """Build a standard CloudWatch metric query."""
        logger.info(f'Using standard GetMetricData for {namespace}/{metric_name}')
        logger.info(f'Dimensions: {[f"{d.name}={d.value}" for d in dimensions]}')

        # Map statistic to standard CloudWatch format
        cloudwatch_statistic = self._map_to_cloudwatch_statistic(statistic)

        # Convert dimensions to CloudWatch format
        cw_dimensions = [{'Name': d.name, 'Value': d.value} for d in dimensions]

        return {
            'Id': 'm1',
            'MetricStat': {
                'Metric': {
                    'Namespace': namespace,
                    'MetricName': metric_name,
                    'Dimensions': cw_dimensions,
                },
                'Period': period,
                'Stat': cloudwatch_statistic,
            },
            'ReturnData': True,
        }

    def _process_metric_data_response(self, response):
        """Process the GetMetricData API response."""
        metric_data_results = []

        for result in response.get('MetricDataResults', []):
            # Process timestamps and values into data points
            datapoints = []
            timestamps = result.get('Timestamps', [])
            values = result.get('Values', [])

            for ts, val in zip(timestamps, values):
                datapoints.append(MetricDataPoint(timestamp=ts, value=val))

            # Sort datapoints by timestamp
            datapoints.sort(key=lambda x: x.timestamp)

            # Create the metric data result
            metric_result = MetricDataResult(
                id=result.get('Id', ''),
                label=result.get('Label', ''),
                statusCode=result.get('StatusCode', 'Complete'),
                datapoints=datapoints,
                messages=result.get('Messages', []),
            )
            metric_data_results.append(metric_result)

        # Create and return the response
        return GetMetricDataResponse(
            metricDataResults=metric_data_results, messages=response.get('Messages', [])
        )

    def _map_to_metrics_insights_statistic(self, statistic):
        """Map and validate a statistic for Metrics Insights."""
        statistic_mapping = {
            'Average': 'AVG',
            'Sum': 'SUM',
            'Maximum': 'MAX',
            'Minimum': 'MIN',
            'SampleCount': 'COUNT',
        }

        metrics_insights_statistic = statistic_mapping.get(statistic, statistic.upper())
        self._validate_metrics_insights_statistic(metrics_insights_statistic)
        return metrics_insights_statistic

    def _validate_metrics_insights_statistic(self, statistic):
        """Validate that a statistic is valid for Metrics Insights."""
        valid_statistics = ['AVG', 'COUNT', 'MAX', 'MIN', 'SUM']
        if statistic not in valid_statistics:
            raise ValueError(
                f'Invalid statistic for Metrics Insights: {statistic}. Must be one of {", ".join(valid_statistics)}'
            )

    def _map_to_cloudwatch_statistic(self, statistic):
        """Map a statistic to the standard CloudWatch format."""
        statistic_mapping = {
            'AVG': 'Average',
            'SUM': 'Sum',
            'MAX': 'Maximum',
            'MIN': 'Minimum',
            'COUNT': 'SampleCount',
        }

        return statistic_mapping.get(statistic, statistic)

    def _build_schema_string(self, namespace, schema_dimension_keys):
        """Build the SCHEMA part of a Metrics Insights query."""
        schema_parts = [f'"{namespace}"']

        if schema_dimension_keys:
            dimension_parts = [f'"{key}"' for key in schema_dimension_keys]
            schema_parts.extend(dimension_parts)

        return ', '.join(schema_parts)

    def _build_where_clause(self, dimensions):
        """Build the WHERE clause for a Metrics Insights query."""
        if not dimensions:
            return None

        dimension_filters = [f'"{dim.name}"=\'{dim.value}\'' for dim in dimensions]
        return f'WHERE {" AND ".join(dimension_filters)}'

    @DecoratorManager.exception_handler()
    async def get_metric_metadata(
        self,
        ctx: Context,
        namespace: str = Field(
            ..., description="The namespace of the metric (e.g., 'AWS/EC2', 'AWS/Lambda')"
        ),
        metric_name: str = Field(
            ..., description="The name of the metric (e.g., 'CPUUtilization', 'Duration')"
        ),
        region: Annotated[
            str,
            Field(
                description='AWS region for consistency. Note: This function uses local metadata and does not make AWS API calls. Defaults to us-east-1.'
            ),
        ] = 'us-east-1',
    ) -> Optional[MetricMetadata]:
        """Gets metadata for a CloudWatch metric including description, unit and recommended
        statistics that can be used for metric data retrieval."""
        try:
            # Log the metric information for debugging
            logger.info(f'Getting metadata for metric: {namespace}/{metric_name}')

            # Look up metadata from the loaded index
            metadata = self._lookup_metadata(namespace, metric_name)

            if metadata:
                logger.info(f'Found metadata for {namespace}/{metric_name}')

                # Extract the required fields from metadata
                description = metadata.get('description', '')
                recommended_statistics = metadata.get('recommendedStatistics', '')
                unit = metadata.get('unitInfo', '')

                # Return populated MetricMetadata object
                return MetricMetadata(
                    description=description,
                    recommendedStatistics=recommended_statistics,
                    unit=unit,
                )
            else:
                logger.info(f'No metadata found for {namespace}/{metric_name}')
                return None

        except Exception as e:
            logger.error(f'Error in get_metric_metadata: {str(e)}')
            await ctx.error(f'Error getting metric metadata: {str(e)}')
            raise

    @DecoratorManager.exception_handler()
    async def get_recommended_metric_alarms(
        self,
        ctx: Context,
        namespace: str = Field(
            ..., description="The namespace of the metric (e.g., 'AWS/EC2', 'AWS/Lambda')"
        ),
        metric_name: str = Field(
            ..., description="The name of the metric (e.g., 'CPUUtilization', 'Duration')"
        ),
        dimensions: List[Dimension] = Field(
            default_factory=list,
            description='List of dimensions that identify the metric, each with name and value',
        ),
        region: Annotated[
            str,
            Field(
                description='AWS region for consistency. Note: This function uses local metadata and does not make AWS API calls. Defaults to us-east-1.'
            ),
        ] = 'us-east-1',
    ) -> List[AlarmRecommendation]:
        """Gets recommended alarms for a CloudWatch metric."""
        try:
            # Log the metric information for debugging
            logger.info(f'Getting alarm recommendations for metric: {namespace}/{metric_name}')
            logger.info(f'Dimensions: {[f"{d.name}={d.value}" for d in dimensions]}')

            # Look up metadata from the loaded index
            metadata = self._lookup_metadata(namespace, metric_name)

            if not metadata or 'alarmRecommendations' not in metadata:
                logger.info(f'No alarm recommendations found for {namespace}/{metric_name}')
                return []

            alarm_recommendations = metadata['alarmRecommendations']
            logger.info(
                f'Found {len(alarm_recommendations)} alarm recommendations for {namespace}/{metric_name}'
            )

            # Filter recommendations based on provided dimensions
            matching_recommendations = []
            provided_dims = {dim.name: dim.value for dim in dimensions}

            for alarm_data in alarm_recommendations:
                if self._alarm_matches_dimensions(alarm_data, provided_dims):
                    try:
                        # Parse the alarm recommendation data
                        alarm_rec = self._parse_alarm_recommendation(alarm_data)
                        matching_recommendations.append(alarm_rec)
                    except Exception as e:
                        logger.warning(f'Error parsing alarm recommendation: {e}')
                        continue

            logger.info(
                f'Returning {len(matching_recommendations)} matching alarm recommendations'
            )
            return matching_recommendations

        except Exception as e:
            logger.error(f'Error in get_recommended_metric_alarms: {str(e)}')
            await ctx.error(f'Error getting alarm recommendations: {str(e)}')
            raise

    def _alarm_matches_dimensions(
        self, alarm_data: Dict[str, Any], provided_dims: Dict[str, str]
    ) -> bool:
        """Check if an alarm recommendation matches the provided dimensions."""
        alarm_dimensions = alarm_data.get('dimensions', [])

        # If alarm has no dimension requirements, it matches any dimensions
        if not alarm_dimensions:
            return True

        # Check if all alarm dimension requirements are satisfied
        for alarm_dim in alarm_dimensions:
            dim_name = alarm_dim.get('name')
            if not dim_name:
                continue

            # If alarm dimension has a specific value requirement
            if 'value' in alarm_dim:
                required_value = alarm_dim['value']
                if dim_name not in provided_dims or provided_dims[dim_name] != required_value:
                    return False
            else:
                # If alarm dimension has no specific value, just check if dimension name exists
                if dim_name not in provided_dims:
                    return False

        return True

    def _parse_alarm_recommendation(self, alarm_data: Dict[str, Any]) -> AlarmRecommendation:
        """Parse alarm recommendation data into AlarmRecommendation object."""
        # Parse threshold
        threshold_data = alarm_data.get('threshold', {})
        threshold = AlarmRecommendationThreshold(
            staticValue=threshold_data.get('staticValue', 0.0),
            justification=threshold_data.get('justification', ''),
        )

        # Parse dimensions
        dimensions = []
        for dim_data in alarm_data.get('dimensions', []):
            alarm_dim = AlarmRecommendationDimension(
                name=dim_data.get('name', ''),
                value=dim_data.get('value') if 'value' in dim_data else None,
            )
            dimensions.append(alarm_dim)

        # Create alarm recommendation
        return AlarmRecommendation(
            alarmDescription=alarm_data.get('alarmDescription', ''),
            threshold=threshold,
            period=alarm_data.get('period', 300),
            comparisonOperator=alarm_data.get('comparisonOperator', ''),
            statistic=alarm_data.get('statistic', ''),
            evaluationPeriods=alarm_data.get('evaluationPeriods', 1),
            datapointsToAlarm=alarm_data.get('datapointsToAlarm', 1),
            treatMissingData=alarm_data.get('treatMissingData', 'missing'),
            dimensions=dimensions,
            intent=alarm_data.get('intent', ''),
        )
