import json

import pytest
from interfaces.grafana_datasource_exchange.v0.schema import GrafanaDatasource
from ops import CharmBase, Framework
from scenario import Context, Relation, State
from scenario.errors import UncaughtCharmError

from cosl.interfaces.datasource_exchange import DatasourceExchange, DSExchangeAppData


@pytest.mark.parametrize(
    "meta, invalid_reason",
    (
        (
            {
                "requires": {"boo": {"interface": "gibberish"}},
                "provides": {"far": {"interface": "grafana_datasource_exchange"}},
            },
            "unexpected interface 'gibberish'",
        ),
        (
            {
                "requires": {"boo": {"interface": "grafana_datasource_exchange"}},
                "provides": {"goo": {"interface": "grafana_datasource_exchange"}},
            },
            "endpoint 'far' not declared",
        ),
    ),
)
def test_endpoint_validation(meta, invalid_reason):
    class BadCharm(CharmBase):
        def __init__(self, framework: Framework):
            super().__init__(framework)
            self.ds_exchange = DatasourceExchange(
                self, provider_endpoint="far", requirer_endpoint="boo"
            )

    with pytest.raises(UncaughtCharmError, match=invalid_reason):
        ctx = Context(BadCharm, meta={"name": "bob", **meta})
        ctx.run(ctx.on.update_status(), State())


def test_ds_submit():
    # GIVEN a charm with a single datasource_exchange relation
    class MyCharm(CharmBase):
        META = {
            "name": "robbie",
            "provides": {"foo": {"interface": "grafana_datasource_exchange"}},
            "requires": {"bar": {"interface": "grafana_datasource_exchange"}},
        }

        def __init__(self, framework: Framework):
            super().__init__(framework)
            self.ds_exchange = DatasourceExchange(
                self, provider_endpoint="foo", requirer_endpoint="bar"
            )
            self.ds_exchange.submit([{"type": "tempo", "uid": "123"}])

    ctx = Context(MyCharm, meta=MyCharm.META)

    dse_in = Relation("foo")
    state_in = State(relations={dse_in}, leader=True)

    # WHEN we receive any event
    state_out = ctx.run(ctx.on.update_status(), state_in)

    # THEN we publish in our app databags any datasources we're aware of
    dse_out = state_out.get_relation(dse_in.id)
    assert dse_out.local_app_data
    data = DSExchangeAppData.load(dse_out.local_app_data)
    assert data.datasources[0].type == "tempo"
    assert data.datasources[0].uid == "123"


def test_ds_receive():
    # GIVEN a charm with a single datasource_exchange relation
    class MyCharm(CharmBase):
        META = {
            "name": "robbie",
            "provides": {"foo": {"interface": "grafana_datasource_exchange"}},
            "requires": {"bar": {"interface": "grafana_datasource_exchange"}},
        }

        def __init__(self, framework: Framework):
            super().__init__(framework)
            self.ds_exchange = DatasourceExchange(
                self, provider_endpoint="foo", requirer_endpoint="bar"
            )

    ctx = Context(MyCharm, meta=MyCharm.META)

    ds_requirer_in = [
        {"type": "c", "uid": "3"},
        {"type": "a", "uid": "1"},
        {"type": "b", "uid": "2"},
    ]
    ds_provider_in = [{"type": "d", "uid": "4"}]

    dse_requirer_in = Relation(
        "foo",
        remote_app_data=DSExchangeAppData(
            datasources=json.dumps(sorted(ds_provider_in, key=lambda raw_ds: raw_ds["uid"]))
        ).dump(),
    )
    dse_provider_in = Relation(
        "bar",
        remote_app_data=DSExchangeAppData(
            datasources=json.dumps(sorted(ds_requirer_in, key=lambda raw_ds: raw_ds["uid"]))
        ).dump(),
    )
    state_in = State(relations={dse_requirer_in, dse_provider_in}, leader=True)

    # WHEN we receive any event
    with ctx(ctx.on.update_status(), state_in) as mgr:
        # THEN we can access all datasources we're given
        dss = mgr.charm.ds_exchange.received_datasources
        assert [ds.type for ds in dss] == list("abcd")
        assert [ds.uid for ds in dss] == list("1234")
        assert isinstance(dss[0], GrafanaDatasource)
