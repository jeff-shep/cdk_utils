from typing import Any, Dict, List

from aws_cdk import aws_cloudwatch

ALARM_STATE_OK = "OK"
ALARM_STATE_ALARM = "ALARM"

BREACHING_RULES = [
    lambda defn, metric: defn.treat_missing_data == aws_cloudwatch.TreatMissingData.BREACHING and metric is None,
    lambda defn, metric: defn.comparison_operator == aws_cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD
    and metric < defn.threshold,
    lambda defn, metric: defn.comparison_operator == aws_cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD
    and metric <= defn.threshold,
    lambda defn, metric: defn.comparison_operator
    == aws_cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD
    and metric >= defn.threshold,
    lambda defn, metric: defn.comparison_operator == aws_cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
    and metric > defn.threshold,
]


class MetricException(Exception):
    pass


class CloudWatchAlarmSimulator:
    def __init__(self, alarm_definition: aws_cloudwatch.AlarmProps):
        self.alarm_definition = alarm_definition

    def run_simulation(self, metrics: List[Dict[str, Any]]) -> Dict[int, str]:
        for metric in metrics:
            if metric["metric"] == self.alarm_definition.metric:
                return {i: self.check_evaluation_period(i, metric["values"]) for i in range(len(metric["values"]))}
        raise MetricException(f"Metric {self.alarm_definition.metric} not found!")

    def check_evaluation_period(self, period: int, metric_values: List[float]) -> str:
        evaluation_periods = int(self.alarm_definition.evaluation_periods)
        metric_set = metric_values[max(1 + period - evaluation_periods, 0) : period + 1]
        if all(self.check_breaching(metric) for metric in metric_set):
            return ALARM_STATE_ALARM
        return ALARM_STATE_OK

    def check_breaching(self, metric: float) -> bool:
        for rule in BREACHING_RULES:
            if rule(self.alarm_definition, metric):  # type: ignore
                return True
        return False

    @staticmethod
    def make_simulation_result(length: int, alarm: List[int]) -> Dict[int, str]:
        return {i: "ALARM" if i in alarm else "OK" for i in range(length)}
