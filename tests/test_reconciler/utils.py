def get_observed_events(observe_mock):
    return {call.args[0].event_type for call in observe_mock.call_args_list}
