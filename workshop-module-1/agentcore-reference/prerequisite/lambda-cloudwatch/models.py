"""Models for CloudWatch integration."""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Dict, List, Optional, Set, Union


# CloudWatch Logs Models
class LogGroupMetadata(BaseModel):
    """Metadata for a CloudWatch log group."""
    logGroupName: str
    creationTime: datetime
    retentionInDays: Optional[int] = None
    storedBytes: int
    kmsKeyId: Optional[str] = None
    dataProtectionStatus: Optional[str] = None
    logGroupClass: Optional[str] = None
    logGroupArn: str


class SavedLogsInsightsQuery(BaseModel):
    """A saved CloudWatch Logs Insights query."""
    model_config = ConfigDict(populate_by_name=True)
    
    queryId: str = Field(..., alias="queryDefinitionId")
    name: str
    queryString: str
    logGroupNames: Set[str] = set()
    logGroupPrefixes: Set[str] = set()


class LogsMetadata(BaseModel):
    """Metadata about CloudWatch Logs."""
    log_group_metadata: List[LogGroupMetadata]
    saved_queries: List[SavedLogsInsightsQuery] = []


class LogsQueryCancelResult(BaseModel):
    """Result of canceling a CloudWatch Logs Insights query."""
    success: bool


class LogAnomalyDetector(BaseModel):
    """A CloudWatch Logs anomaly detector."""
    anomalyDetectorArn: str
    anomalyDetectorName: str
    evaluationFrequency: Optional[str] = None
    filterPattern: Optional[str] = None
    kmsKeyId: Optional[str] = None
    detectorStatus: Optional[str] = None
    creationTimeStamp: Optional[datetime] = None
    lastModifiedTimeStamp: Optional[datetime] = None
    anomalyVisibilityTime: Optional[int] = None


class LogAnomaly(BaseModel):
    """A CloudWatch Logs anomaly."""
    anomalyId: str
    patternId: str
    anomalyDetectorArn: str
    pattern: str
    patternString: str
    firstSeen: str  # ISO datetime string
    lastSeen: str  # ISO datetime string
    description: str
    active: bool
    anomalyScore: Optional[float] = None
    logGroupArnList: List[str]
    numberOfLogGroups: Optional[int] = None
    minimumMatchedLogItems: Optional[int] = None
    maximumMatchedLogItems: Optional[int] = None
    averageMatchedLogItems: Optional[int] = None
    logExcerpt: Optional[str] = None
    suppressedUntil: Optional[str] = None


class LogAnomalyResults(BaseModel):
    """Results of anomaly detection in CloudWatch Logs."""
    anomaly_detectors: List[LogAnomalyDetector]
    anomalies: List[LogAnomaly]


class QueryResults(BaseModel):
    """Results of a CloudWatch Logs Insights query."""
    columns: List[str]
    data: List[List[Optional[str]]]


class LogsAnalysisResult(BaseModel):
    """Results of analyzing a CloudWatch log group."""
    log_anomaly_results: LogAnomalyResults
    top_patterns: Dict[str, Any]  # Query results for most common message patterns
    top_patterns_containing_errors: Dict[str, Any]  # Query results for patterns containing errors


# CloudWatch Metrics Models
class Dimension(BaseModel):
    """A CloudWatch metric dimension."""
    name: str = Field(..., description="The name of the dimension")
    value: str = Field(..., description="The value of the dimension")


class MetricDataPoint(BaseModel):
    """A single CloudWatch metric data point."""
    timestamp: datetime
    value: float


class MetricDataResult(BaseModel):
    """Result of a CloudWatch GetMetricData API call for a single metric."""
    id: str
    label: str
    statusCode: str = "Complete"
    datapoints: List[MetricDataPoint] = []
    messages: List[Dict[str, str]] = []


class GetMetricDataResponse(BaseModel):
    """Response from CloudWatch GetMetricData API."""
    metricDataResults: List[MetricDataResult]
    messages: List[Dict[str, str]] = []


class MetricMetadataIndexKey(BaseModel):
    """Key for indexing CloudWatch metric metadata."""
    namespace: str
    metric_name: str


class MetricMetadata(BaseModel):
    """Metadata for a CloudWatch metric."""
    description: str
    recommendedStatistics: str
    unit: str


# CloudWatch Alarms Models
class AlarmRecommendationThreshold(BaseModel):
    """Threshold for a CloudWatch alarm recommendation."""
    staticValue: float
    justification: str


class AlarmRecommendationDimension(BaseModel):
    """Dimension for a CloudWatch alarm recommendation."""
    name: str
    value: Optional[str] = None


class AlarmRecommendation(BaseModel):
    """A recommendation for a CloudWatch alarm."""
    alarmDescription: str
    threshold: AlarmRecommendationThreshold
    period: int
    comparisonOperator: str
    statistic: str
    evaluationPeriods: int
    datapointsToAlarm: int
    treatMissingData: str
    dimensions: List[AlarmRecommendationDimension]
    intent: str


class MetricAlarmSummary(BaseModel):
    """Summary information for a CloudWatch metric alarm."""
    alarm_name: str
    alarm_description: Optional[str] = None
    state_value: str
    state_reason: str
    metric_name: str
    namespace: str
    dimensions: List[Dict[str, str]] = []
    threshold: float
    comparison_operator: str
    state_updated_timestamp: datetime


class CompositeAlarmSummary(BaseModel):
    """Summary information for a CloudWatch composite alarm."""
    alarm_name: str
    alarm_description: Optional[str] = None
    state_value: str
    state_reason: str
    alarm_rule: str
    state_updated_timestamp: datetime


class ActiveAlarmsResponse(BaseModel):
    """Response containing active CloudWatch alarms."""
    metric_alarms: List[MetricAlarmSummary] = []
    composite_alarms: List[CompositeAlarmSummary] = []
    has_more_results: bool = False
    message: Optional[str] = None


class AlarmDetails(BaseModel):
    """Detailed information about a CloudWatch alarm."""
    alarm_name: str
    alarm_description: Optional[str] = None
    alarm_type: str  # MetricAlarm or CompositeAlarm
    current_state: str
    metric_name: Optional[str] = None
    namespace: Optional[str] = None
    dimensions: Optional[List[Dict[str, str]]] = None
    threshold: Optional[float] = None
    comparison_operator: Optional[str] = None
    evaluation_periods: Optional[int] = None
    period: Optional[int] = None
    statistic: Optional[str] = None
    alarm_rule: Optional[str] = None


class AlarmHistoryItem(BaseModel):
    """A CloudWatch alarm history item."""
    alarm_name: str
    alarm_type: str
    timestamp: datetime
    history_item_type: str
    history_summary: str
    old_state: Optional[str] = None
    new_state: Optional[str] = None
    state_reason: Optional[str] = None


class TimeRangeSuggestion(BaseModel):
    """A suggested time range for investigating CloudWatch alarms."""
    start_time: datetime
    end_time: datetime
    reason: str


class AlarmHistoryResponse(BaseModel):
    """Response containing CloudWatch alarm history."""
    alarm_details: AlarmDetails
    history_items: List[AlarmHistoryItem] = []
    time_range_suggestions: List[TimeRangeSuggestion] = []
    has_more_results: bool = False
    message: Optional[str] = None


class CompositeAlarmComponentResponse(BaseModel):
    """Response containing information about components of a composite alarm."""
    composite_alarm_name: str
    component_alarms: List[str]
    alarm_rule: str
    component_details: Optional[List[AlarmDetails]] = None
