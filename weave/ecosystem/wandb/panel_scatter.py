import dataclasses
import inspect
import typing

import weave

from ... import weave_internal

from . import weave_plotly


@weave.type()
class ScatterConfig:
    x_fn: weave.Node[float] = dataclasses.field(
        default_factory=lambda: weave.graph.VoidNode()
    )
    y_fn: weave.Node[float] = dataclasses.field(
        default_factory=lambda: weave.graph.VoidNode()
    )


# This is boilerplate that I'd like to get rid of.
def scatter_set_default_config(config, input_node, new_config):
    return new_config


# TODO: really annoying that I need the setter here.
@weave.op(setter=scatter_set_default_config)
def scatter_default_config(
    config: typing.Optional[ScatterConfig],
    unnested_node: list[typing.Any],
) -> ScatterConfig:
    input_type_item_type = weave.type_of(unnested_node).object_type
    if config == None:
        return ScatterConfig(
            x_fn=weave.define_fn({"item": input_type_item_type}, lambda item: item),
            y_fn=weave.define_fn({"item": input_type_item_type}, lambda item: item),
        )
    return config


# The render op. This renders the panel.
@weave.op(name="Scatter")
def scatter(
    input_node: weave.Node[list[typing.Any]], config: ScatterConfig
) -> weave_plotly.PanelPlotly:
    unnested = weave.ops.unnest(input_node)
    config = scatter_default_config(config, unnested)
    plot_data = unnested.map(
        lambda item: weave.ops.dict_(x=config.x_fn(item), y=config.y_fn(item))
    )
    fig = weave_plotly.plotly_scatter(plot_data)
    return weave_plotly.PanelPlotly(fig)


# The config render op. This renders the config editor.
@weave.op(name="Scatter_config")
def scatter_config(
    input_node: weave.Node[list[typing.Any]], config: ScatterConfig
) -> weave.panels.Group2:
    unnested = weave.ops.unnest(input_node)
    config = scatter_default_config(config, unnested)
    return weave.panels.Group2(
        items={
            "x_fn": weave.panels.LabeledItem(
                label="x",
                item=weave.panels.ExpressionEditor(
                    config=weave.panels.ExpressionEditorConfig(config.x_fn)
                ),
            ),
            "y_fn": weave.panels.LabeledItem(
                label="y",
                item=weave.panels.ExpressionEditor(
                    config=weave.panels.ExpressionEditorConfig(config.y_fn)
                ),
            ),
        }
    )


# The interface for constructing this Panel from Python
@weave.type()
class Scatter(weave.Panel):
    id = "Scatter"
    config: typing.Optional[ScatterConfig] = None
    _renderAsPanel: weave_plotly.PanelPlotly = dataclasses.field(
        default_factory=lambda: None
    )

    def __init__(
        self, input_node, vars=None, config=None, _renderAsPanel=None, **options
    ):
        super().__init__(input_node=input_node, vars=vars)
        self.config = config
        if self.config is None:
            self.config = ScatterConfig()

        self._renderAsPanel = _renderAsPanel
        if self._renderAsPanel is None:
            self._renderAsPanel = weave_plotly.PanelPlotly()
        # self._renderAsPanel = weave_internal.make_var_node(
        #     weave_plotly.PanelPlotly.WeaveType(), "panel"
        # )

        unnested = weave.ops.unnest(self.input_node)
        if "x_fn" in options:
            sig = inspect.signature(options["x_fn"])
            param_name = list(sig.parameters.values())[0].name
            self.config.x_fn = weave.define_fn(
                {param_name: unnested.type.object_type}, options["x_fn"]
            )
        if "y_fn" in options:
            sig = inspect.signature(options["y_fn"])
            param_name = list(sig.parameters.values())[0].name
            self.config.y_fn = weave.define_fn(
                {param_name: unnested.type.object_type}, options["y_fn"]
            )

    @weave.op(output_type=lambda input_type: input_type["self"].input_node.output_type)
    def selected(self):
        unnested = weave.ops.unnest(self.input_node)
        config = scatter_default_config(self.config, unnested)
        filtered = unnested.filter(
            lambda item: weave.ops.Boolean.bool_and(
                weave.ops.Boolean.bool_and(
                    weave.ops.Boolean.bool_and(
                        config.x_fn(item)
                        > weave.ops.TypedDict.pick(
                            self._renderAsPanel.config.selected, "xMin"
                        ),
                        config.x_fn(item)
                        < weave.ops.TypedDict.pick(
                            self._renderAsPanel.config.selected, "xMax"
                        ),
                    ),
                    config.y_fn(item)
                    > weave.ops.TypedDict.pick(
                        self._renderAsPanel.config.selected, "yMin"
                    ),
                ),
                config.y_fn(item)
                < weave.ops.TypedDict.pick(self._renderAsPanel.config.selected, "yMax"),
            )
        )
        return weave_internal.use(filtered)