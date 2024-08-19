import ops
from ops import Framework
from ops.pebble import Layer

from cosl.coordinated_workers.worker import Worker


class WorkerCharm(ops.CharmBase):
    def __init__(self, framework: Framework):
        super().__init__(framework)
        self.worker = Worker(self, "workload", pebble_layer=self._pebble_layer)

    def _pebble_layer(
        self,
        _,
        layer=Layer(
            {
                "summary": "placeholder",
                "description": "does nothing",
                "services": {
                    "foo": {
                        "summary": "placeholder",
                        "description": "does nothing",
                        "command": "sleep infinity",
                        "startup": "enabled",
                    }
                },
            }
        ),
    ):
        return layer


if __name__ == "__main__":
    ops.main.main(WorkerCharm)
