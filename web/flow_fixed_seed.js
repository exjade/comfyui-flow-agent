import { app } from "../../scripts/app.js";

const FIXED_SEED_NODES = new Set(["FlowNanoBanana"]);

function forceFixedSeed(node) {
    const seedWidget = node.widgets?.find((widget) => widget.name === "seed");
    if (seedWidget) {
        seedWidget.value = 43;
    }

    const controlWidget = node.widgets?.find(
        (widget) => widget.name === "control_after_generate",
    );
    if (controlWidget) {
        controlWidget.value = "fixed";
    }
}

app.registerExtension({
    name: "comfyui-flow-agent.fixed-image-seed",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!FIXED_SEED_NODES.has(nodeData.name)) {
            return;
        }

        const previousCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            previousCreated?.apply(this, arguments);
            forceFixedSeed(this);
        };

        const previousConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            previousConfigure?.apply(this, arguments);
            forceFixedSeed(this);
        };
    },
});
