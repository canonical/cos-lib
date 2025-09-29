from ops.framework import StoredDict, StoredList

from cosl.types import type_convert_stored


def test_converting_stored_types():
    assert type_convert_stored(StoredDict({}, under={1: {}})) == {1: {}}
    assert type_convert_stored(StoredDict({}, under={1: []})) == {1: []}
    assert type_convert_stored(StoredDict({}, under={1: 2})) == {1: 2}
    assert type_convert_stored(StoredList({}, under=[1, 2])) == [1, 2]
