# Test helpers

This subpackage contains test helpers for CDK code

## CloudWatchAlarmSimulator

This is designed to simulate the behaviour of a CloudWatch alarm.
In order to use it, you should have access to an aws_cloudwatch.AlarmProps object, which is initialised with the same properties your alarm is using.
These are available within the constructs provided in this library as alarm.alarm_props, but if you create an alarm without using these, you will have to set it up yourself.

Currently this library only supports testing of single metric alarms.

Usage example:
```python
from cdkutils.test_helpers import CloudWatchAlarmSimulator


icing_alarm_props = test_dashboard_stack.alarm.alarm_props
cloudwatch_alarm_simulator = CloudWatchAlarmSimulator(icing_alarm_props)
        
# Alarm is configured with 144 evaluation periods, so we expect it to start alerting 144 after start of
# each outage period
evaluation_periods = icing_alarm_props.evaluation_periods
no_files_first_start = 20
no_files_first_end = 170
no_files_second_start = 190
no_files_second_end = 343
first_alert_expected = no_files_first_start + evaluation_periods
second_alert_expected = no_files_second_start + evaluation_periods

alerting_metric_values = [0 if no_files_first_start < i < no_files_first_end or no_files_second_start < i < no_files_second_end else 1 for i in range(350)]
alerting_metrics = {"metric": icing_alarm_props.metric, "values": alerting_metric_values}
alarm_states = cloudwatch_alarm_simulator.run_simulation([alerting_metrics])
expected_alarm_states = CloudWatchAlarmSimulator.make_simulation_result(len(alerting_metric_values), list(range(first_alert_expected, no_files_first_end)) + list(range(second_alert_expected, no_files_second_end)))
self.assertEqual(alarm_states, expected_alarm_states)
```