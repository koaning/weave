import weave.weave_types
from .. import weave_types as types
from .. import runs
from ..ops_primitives import _dict_utils
from rich import print


def test_typeof_string():
    t = types.TypeRegistry.type_of("x")
    assert t == types.String()


def test_typeof_list_const_string():
    t = types.TypeRegistry.type_of(["x"])
    assert t == types.List(types.String())


def test_serialize_const_string():
    t = types.Const(types.String(), "x")
    ser = t.to_dict()
    deser = types.TypeRegistry.type_from_dict(ser)
    assert t == deser


def test_merge_typedict_keys_are_stable():
    for i in range(10):
        t = types.TypedDict(
            {"a": types.String(), "b": types.String(), "c": types.String()}
        )
        t2 = types.TypedDict(
            {"a": types.String(), "b": types.String(), "c": types.String()}
        )
        r = types.merge_types(t, t2)
        assert list(r.property_types.keys()) == ["a", "b", "c"]


def test_typeof_bool():
    assert types.TypeRegistry.type_of(False) == types.Boolean()


def test_typeof_type():
    assert types.TypeRegistry.type_of(types.Int()) == types.Type()


def test_type_tofromdict():
    assert types.Type().to_dict() == "type"
    assert types.TypeRegistry.type_from_dict("type") == types.Type()


def test_typeof_list_runs():
    l = [
        runs.Run("a", "op", inputs={"a": "x"}, output=4.9),
        runs.Run("b", "op", inputs={"a": "x", "b": 9}, output=3.3),
    ]
    actual = types.TypeRegistry.type_of(l)
    print("test_typeof_list_runs.actual", actual)

    assert actual == types.List(
        types.UnionType(
            types.RunType(
                inputs=types.TypedDict({"a": types.String()}),
                history=types.List(types.UnknownType()),
                output=types.Float(),
            ),
            types.RunType(
                inputs=types.TypedDict({"a": types.String(), "b": types.Int()}),
                history=types.List(types.UnknownType()),
                output=types.Float(),
            ),
        )
    )


def test_typeof_list_dict_merge():
    d = [{"a": 6, "b": "x"}, {"a": 5, "b": None}]
    assert types.TypeRegistry.type_of(d) == types.List(
        types.TypedDict({"a": types.Int(), "b": types.optional(types.String())})
    )


def test_typeof_nested_dict_merge():
    t1 = weave.weave_types.TypedDict(
        {"a": weave.weave_types.TypedDict({"b": types.Int()})}
    )
    t2 = weave.weave_types.TypedDict(
        {"a": weave.weave_types.TypedDict({"c": types.String()})}
    )
    merged_type = _dict_utils.typeddict_merge_output_type({"self": t1, "other": t2})
    assert merged_type == weave.weave_types.TypedDict(
        {"a": weave.weave_types.TypedDict({"b": types.Int(), "c": types.String()})}
    )