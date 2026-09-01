import { app } from "../../scripts/app.js";

function setSocketVisible(input, visible) {
    if (!input) return;
    input.flowUploadOriginalLabel ??= input.label;
    input.flowUploadOriginalColorOn ??= input.color_on;
    input.flowUploadOriginalColorOff ??= input.color_off;
    input.label = visible ? input.flowUploadOriginalLabel : "";
    input.color_on = visible ? input.flowUploadOriginalColorOn : "#202020";
    input.color_off = visible ? input.flowUploadOriginalColorOff : "#202020";
}

function applyMediaType(node) {
    const mediaType = String(
        node.widgets?.find((widget) => widget.name === "media_type")?.value || "image",
    );
    for (const input of node.inputs || []) {
        if (input.name === "image" || input.name === "video") {
            setSocketVisible(input, input.name === mediaType);
        }
    }
    if (node.flowUploadMediaHelp) {
        node.flowUploadMediaHelp.textContent = mediaType === "video"
            ? "Connect VIDEO or provide one video path · image input disabled"
            : "Connect IMAGE or provide one image path · video input disabled";
    }
    const size = node.computeSize?.();
    if (size) node.setSize([Math.max(node.size[0], 360), size[1]]);
    node.setDirtyCanvas?.(true, true);
}

function installMediaTypeBehavior(node) {
    if (!node.flowUploadMediaHelp) {
        const label = document.createElement("div");
        label.style.boxSizing = "border-box";
        label.style.width = "100%";
        label.style.padding = "6px 10px";
        label.style.borderRadius = "6px";
        label.style.background = "#171717";
        label.style.color = "#9fc8ff";
        label.style.fontSize = "12px";
        const helpWidget = node.addDOMWidget(
            "flow_upload_media_help",
            "selected media",
            label,
            { hideOnZoom: false, getMinHeight: () => 30, getMaxHeight: () => 30 },
        );
        helpWidget.serialize = false;
        node.flowUploadMediaHelp = label;
    }

    const typeWidget = node.widgets?.find((widget) => widget.name === "media_type");
    if (typeWidget && !typeWidget.flowUploadCallbackWrapped) {
        const previousCallback = typeWidget.callback;
        typeWidget.callback = function () {
            previousCallback?.apply(this, arguments);
            applyMediaType(node);
        };
        typeWidget.flowUploadCallbackWrapped = true;
    }
    queueMicrotask(() => applyMediaType(node));
}

app.registerExtension({
    name: "comfyui-flow-agent.upload-media-type",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "FlowUploadMedia") return;

        const previousCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            previousCreated?.apply(this, arguments);
            installMediaTypeBehavior(this);
        };

        const previousConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            previousConfigure?.apply(this, arguments);
            installMediaTypeBehavior(this);
        };
    },
});
