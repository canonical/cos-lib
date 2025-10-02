from ops.framework import StoredDict, StoredList

from cosl.types import type_convert_stored


def test_converting_stored_types():
    # GIVEN empty structures
    assert type_convert_stored(StoredDict({}, under={})) == {}
    assert type_convert_stored(StoredList({}, under=[])) == []

    # GIVEN simple key-value pairs
    assert type_convert_stored(StoredDict({}, under={1: {}})) == {1: {}}
    assert type_convert_stored(StoredDict({}, under={1: []})) == {1: []}
    assert type_convert_stored(StoredDict({}, under={1: 2})) == {1: 2}

    # GIVEN nested structures and mixed types
    assert type_convert_stored(StoredList({}, under=[1, StoredList({}, under=[3, 4])])) == [
        1,
        [3, 4],
    ]
    assert type_convert_stored(StoredDict({}, under={1: StoredList({}, under=[3, 4])})) == {
        1: [3, 4]
    }
    assert type_convert_stored(StoredDict({}, under={1: StoredDict({}, under={2: 3})})) == {
        1: {2: 3}
    }
    assert type_convert_stored(StoredList({}, under=[1, StoredDict({}, under={2: 3})])) == [
        1,
        {2: 3},
    ]

    # GIVEN non-standard types
    assert type_convert_stored(StoredDict({}, under={1: "string", 2: 3.5})) == {
        1: "string",
        2: 3.5,
    }
    assert type_convert_stored(StoredList({}, under=[None, True, False])) == [None, True, False]

    # GIVEN deeply nested structures
    assert type_convert_stored(
        StoredDict(
            {},
            under={
                1: StoredList({}, under=[StoredDict({}, under={2: StoredList({}, under=[5])})])
            },
        )
    ) == {1: [{2: [5]}]}
