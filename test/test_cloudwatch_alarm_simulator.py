import unittest

from aws_cdk import aws_cloudwatch, core
from parameterized import parameterized

from cdkutils.test_helpers import CloudWatchAlarmSimulator, MetricException

TEST_METRIC = aws_cloudwatch.Metric(
    metric_name="PutRequests",
    namespace="AWS/S3",
    dimensions={
        "BucketName": "test_bucket",
        "FilterId": "test_filter",
    },
)
STALE_DATA_ALARM_DEFINITION = aws_cloudwatch.AlarmProps(
    evaluation_periods=3,
    statistic="sum",
    metric=TEST_METRIC,
    period=core.Duration.minutes(5),
    threshold=1,
    comparison_operator=aws_cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
    treat_missing_data=aws_cloudwatch.TreatMissingData.BREACHING,
)
DATA_STALE_AFTER_5_PERIODS = [{"metric": TEST_METRIC, "values": [1, 1, 0, 0, 0, 1]}]
DATA_STALE_AFTER_5_PERIODS_RESULT = CloudWatchAlarmSimulator.make_simulation_result(length=6, alarm=[4])
DATA_WRONG_METRIC = [{"metric": aws_cloudwatch.Metric(metric_name="bad_metric", namespace="bad"), "values": [1, 1, 1]}]
DATA_WRONG_METRIC_RESULT = MetricException(f"Metric {TEST_METRIC} not found!")
DATA_STALE_TWICE = [{"metric": TEST_METRIC, "values": [1, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0]}]
DATA_STALE_TWICE_RESULT = CloudWatchAlarmSimulator.make_simulation_result(length=12, alarm=[4, 8])
DATA_NEVER_STALE = [{"metric": TEST_METRIC, "values": [1, 1, 0, 1, 0, 1, 0, 1, 0, 1, 1, 0]}]
DATA_NEVER_STALE_RESULT = CloudWatchAlarmSimulator.make_simulation_result(length=12, alarm=[])
DATA_MISSING_VALUES = [{"metric": TEST_METRIC, "values": [1, 1, 0, 1, None, 0, 0, None, 0, 1, 1, 0]}]
DATA_MISSING_VALUES_RESULT = CloudWatchAlarmSimulator.make_simulation_result(length=12, alarm=[6, 7, 8])
DATA_TWO_METRICS = [DATA_WRONG_METRIC[0], {"metric": TEST_METRIC, "values": [1, 1, 0, 0, 0, 1]}]


class CloudWatchAlarmSimulatorTestBase(unittest.TestCase):
    def run_test_definition_with_metrics(self, alarm_definition, metrics, expected_result):
        alarm_simulator = CloudWatchAlarmSimulator(alarm_definition)
        if isinstance(expected_result, Exception):
            with self.assertRaises(Exception) as e:
                alarm_simulator.run_simulation(metrics)
            self.assertEqual(str(e.exception), str(expected_result))
        else:
            result = alarm_simulator.run_simulation(metrics)
            self.assertEqual(result, expected_result)


class TestStaleDataAlarmSimulator(CloudWatchAlarmSimulatorTestBase):
    @parameterized.expand(
        [
            (STALE_DATA_ALARM_DEFINITION, DATA_STALE_AFTER_5_PERIODS, DATA_STALE_AFTER_5_PERIODS_RESULT),
            (STALE_DATA_ALARM_DEFINITION, DATA_WRONG_METRIC, DATA_WRONG_METRIC_RESULT),
            (STALE_DATA_ALARM_DEFINITION, DATA_STALE_TWICE, DATA_STALE_TWICE_RESULT),
            (STALE_DATA_ALARM_DEFINITION, DATA_NEVER_STALE, DATA_NEVER_STALE_RESULT),
            (STALE_DATA_ALARM_DEFINITION, DATA_MISSING_VALUES, DATA_MISSING_VALUES_RESULT),
            (STALE_DATA_ALARM_DEFINITION, DATA_TWO_METRICS, DATA_STALE_AFTER_5_PERIODS_RESULT),
        ]
    )
    def test_definition_with_metrics(self, alarm_definition, metrics, expected_result):
        self.run_test_definition_with_metrics(alarm_definition, metrics, expected_result)
