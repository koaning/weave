import typing
from . import graph
from . import weave_types as types
from . import stitch
from . import registry_mem
from dataclasses import dataclass
import graphql

if typing.TYPE_CHECKING:
    from . import op_def


@dataclass
class GqlOpPlugin:
    query_fn: typing.Callable[[dict[str, typing.Any], str], str]
    is_root: bool = False


# Ops in `domain_ops` can add this plugin to their op definition to indicate
# that they need data to be fetched from the GQL API. At it's core, the plugin
# allows the user to specify a `query_fn` that takes in the inputs to the op and
# returns a GQL query fragment that is needed by the calling op. The plugin also
# allows the user to specify whether the op is a root op which indicates it is
# the "top" of the GQL query tree. Note, while ops can use this directly (eg.
# see `project_ops.py::artifacts`), most ops use the higher level helpers
# defined in `wb_domain_gql.py`
def wb_gql_op_plugin(
    query_fn: typing.Callable[[dict[str, typing.Any], str], str], is_root: bool = False
) -> dict[str, GqlOpPlugin]:
    return {"wb_domain_gql": GqlOpPlugin(query_fn, is_root)}


# This is the primary exposed function of this module and is called in `compile.py`. It's primary role
# is to roll up all the GQLOps such that a single query can be composed - then replace the root op with a
# special op that calls such query and constructs the correct type. It makes heavy use of the
# `stitch` module to do this. Moreover, all GQL is zipped and deduped so that the minimum request
# is made to the server. See the helper functions below for more details.
def apply_domain_op_gql_translation(leaf_nodes: list[graph.Node]) -> list[graph.Node]:
    # Only apply this transformation at least one of the leaf nodes is a root node
    if not graph.filter_all_nodes(leaf_nodes, _is_root_node):
        return leaf_nodes
    p = stitch.stitch(leaf_nodes)

    def _replace_with_merged_gql(node: graph.Node) -> graph.Node:
        if not _is_root_node(node):
            return node
        node = typing.cast(graph.OutputNode, node)
        query_fragment = _get_fragment(node, p)
        query_str = f"query WeavePythonCG {{ {query_fragment} }}"
        query_str = _normalize_query_str(query_str)
        return graph.OutputNode(
            node.type,
            "gqlroot-wbgqlquery",
            {
                "query_str": graph.ConstNode(types.String(), query_str),
                "output_type": graph.ConstNode(types.Type(), node.type),
            },
        )

    return graph.map_all_nodes(leaf_nodes, _replace_with_merged_gql)


### Everything below are helpers for the above function ###


def _get_gql_plugin(op_def: "op_def.OpDef") -> typing.Optional[GqlOpPlugin]:
    if op_def.plugins is not None and "wb_domain_gql" in op_def.plugins:
        return op_def.plugins["wb_domain_gql"]
    return None


def _get_fragment(node: graph.OutputNode, stitchedGraph: stitch.StitchedGraph) -> str:
    op_def = registry_mem.memory_registry.get_op(node.from_op.name)
    # TODO: make this a helper (it is used in stich.py as well)
    if op_def.derived_from and op_def.derived_from.derived_ops["mapped"] == op_def:
        op_def = op_def.derived_from

    # These are all passthrough ops - should this be in stitch?
    is_passthrough = (
        op_def.name.endswith("offset")
        or op_def.name.endswith("limit")
        or op_def.name.endswith("index")
        or op_def.name.endswith("__getitem__")
        or op_def.name.endswith("concat")
        or op_def.name.endswith("contains")
        or op_def.name.endswith("list")
        or op_def.name.endswith("concat")
        or op_def.name.endswith("flatten")
        or op_def.name.endswith("dropna")
        or op_def.name == "list-createIndexCheckpointTag"
    )

    wb_domain_gql = _get_gql_plugin(op_def)
    if wb_domain_gql is None and not is_passthrough:
        return ""

    forward_obj = stitchedGraph.get_result(node)
    calls = forward_obj.calls
    child_fragment = "\n".join(
        [
            _get_fragment(call.node, stitchedGraph)
            for call in calls
            if isinstance(call.node, graph.OutputNode)
        ]
    )

    if is_passthrough:
        return child_fragment
    wb_domain_gql = typing.cast(GqlOpPlugin, wb_domain_gql)

    const_node_input_vals = {
        key: value.val
        for key, value in node.from_op.inputs.items()
        if isinstance(value, graph.ConstNode)
    }
    return wb_domain_gql.query_fn(
        const_node_input_vals,
        child_fragment,
    )


def _field_selections_are_mergeable(
    selection1: graphql.language.ast.FieldNode,
    selection2: graphql.language.ast.FieldNode,
) -> bool:
    if selection1.name.value != selection2.name.value:
        return False
    if selection1.alias is None and selection2.alias is not None:
        return False
    if selection1.alias is not None and selection2.alias is None:
        return False
    if (
        selection1.alias is not None
        and selection2.alias is not None
        and selection1.alias.value != selection2.alias.value
    ):
        return False
    if len(selection1.arguments) != len(selection2.arguments):
        return False
    for arg1, arg2 in zip(selection1.arguments, selection2.arguments):
        if arg1.name.value != arg2.name.value:
            return False
        if arg1.value.to_dict() != arg2.value.to_dict():
            return False
    return True


def _fragment_selections_are_mergeable(
    selection1: graphql.language.ast.InlineFragmentNode,
    selection2: graphql.language.ast.InlineFragmentNode,
) -> bool:
    return selection1.type_condition.name.value == selection2.type_condition.name.value


def _zip_selection_set(
    selection_set: graphql.language.ast.SelectionSetNode,
) -> graphql.language.ast.SelectionSetNode:
    selections = selection_set.selections
    # Two selections can be merged if their alias, name, and arguments are the same
    # unfortunately, this seems to be O(n^2) in the number of selections
    new_selections: list[
        typing.Union[
            graphql.language.ast.FieldNode, graphql.language.ast.InlineFragmentNode
        ]
    ] = []
    for selection in selections:
        if isinstance(selection, graphql.language.ast.FieldNode) or isinstance(
            selection, graphql.language.ast.InlineFragmentNode
        ):
            for new_selection in new_selections:
                should_merge = (
                    isinstance(selection, graphql.language.ast.FieldNode)
                    and isinstance(new_selection, graphql.language.ast.FieldNode)
                    and _field_selections_are_mergeable(selection, new_selection)
                )
                should_merge = should_merge or (
                    isinstance(selection, graphql.language.ast.InlineFragmentNode)
                    and isinstance(
                        new_selection, graphql.language.ast.InlineFragmentNode
                    )
                    and _fragment_selections_are_mergeable(selection, new_selection)
                )
                if should_merge:
                    if selection.selection_set:
                        if new_selection.selection_set is None:
                            new_selection.selection_set = (
                                graphql.language.ast.SelectionSetNode(selections=())
                            )
                        new_selection.selection_set.selections = (
                            *new_selection.selection_set.selections,
                            *selection.selection_set.selections,
                        )
                    break
            else:
                new_selections.append(selection)
        else:
            raise ValueError(
                f"Found unsupported selection type {type(selection)}, please add implementation in compile_domain.py"
            )
    for selection in new_selections:
        if selection.selection_set:
            selection.selection_set = _zip_selection_set(selection.selection_set)
    selection_set.selections = tuple(new_selections)
    return selection_set


def _zip_gql_doc(
    gql_doc: graphql.language.ast.DocumentNode,
) -> graphql.language.ast.DocumentNode:
    if len(gql_doc.definitions) > 1:
        raise ValueError("Only one query definition is supported")
    query_def = gql_doc.definitions[0]
    if not isinstance(query_def, graphql.language.ast.OperationDefinitionNode):
        raise ValueError("Only operation definitions are supported")

    query_def.selection_set = _zip_selection_set(query_def.selection_set)
    gql_doc.definitions = (query_def,)
    return gql_doc


def _normalize_query_str(query_str: str) -> str:
    gql_doc = graphql.language.parse(query_str)
    gql_doc = _zip_gql_doc(gql_doc)
    return graphql.utilities.strip_ignored_characters(
        graphql.language.print_ast(gql_doc)
    )


def _is_root_node(node: graph.Node) -> bool:
    if not isinstance(node, graph.OutputNode):
        return False

    op_def = registry_mem.memory_registry.get_op(node.from_op.name)
    wb_domain_gql = _get_gql_plugin(op_def)
    return wb_domain_gql is not None and wb_domain_gql.is_root