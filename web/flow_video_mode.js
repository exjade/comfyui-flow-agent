import { app } from "../../scripts/app.js";
import { addFlowLabel } from "./flow_ui_label.js";

const MODE_INPUTS = {
    "text to video": [],
    "start image to video": ["start_image"],
    "first + last frame": ["start_image", "end_image"],
    "ingredients / reference images": [
        "reference_images",
        "reference_image_2",
        "reference_image_3",
        "reference_image_4",
        "reference_image_5",
        "reference_image_6",
        "reference_image_7",
        "reference_image_8",
        "reference_image_9",
        "reference_image_10",
        "reference_media_ids",
        "reference_video_media_ids",
        "reference_video_paths",
        "reference_video",
        "reference_video_2",
        "reference_video_3",
    ],
    "edit source video": [
        "source_video_media_id",
        "source_video_path",
        "source_video",
    ],
    "video to video": [
        "reference_images",
        "reference_image_2",
        "reference_image_3",
        "reference_image_4",
        "reference_image_5",
        "reference_image_6",
        "reference_image_7",
        "reference_image_8",
        "reference_image_9",
        "reference_image_10",
        "reference_media_ids",
        "source_video_media_id",
        "source_video_path",
        "source_video",
    ],
};

const CONDITIONAL_WIDGETS = new Set([
    "reference_media_ids",
    "reference_video_media_ids",
    "reference_video_paths",
    "source_video_media_id",
    "source_video_path",
]);

function setWidgetVisible(widget, visible) {
    if (!widget) return;
    if (!widget.flowOriginalType) {
        widget.flowOriginalType = widget.type;
        widget.flowOriginalComputeSize = widget.computeSize;
    }
    widget.type = visible ? widget.flowOriginalType : "hidden";
    widget.computeSize = visible
        ? widget.flowOriginalComputeSize
        : () => [0, -4];
    widget.hidden = !visible;
    for (const element of [widget.element, widget.inputEl]) {
        if (!element?.style) continue;
        if (element.flowOriginalDisplay === undefined) {
            element.flowOriginalDisplay = element.style.display || "";
        }
        element.style.display = visible ? element.flowOriginalDisplay : "none";
        element.hidden = !visible;
    }
}

function setSocketVisible(input, visible) {
    if (!input) return;
    input.flowOriginalLabel ??= input.label;
    input.flowOriginalColorOn ??= input.color_on;
    input.flowOriginalColorOff ??= input.color_off;
    input.label = visible ? input.flowOriginalLabel : "";
    input.color_on = visible ? input.flowOriginalColorOn : "#202020";
    input.color_off = visible ? input.flowOriginalColorOff : "#202020";
}

function applyVideoMode(node) {
    const mode = String(node.widgets?.find((widget) => widget.name === "mode")?.value || "text to video");
    const active = new Set(MODE_INPUTS[mode] || []);

    for (const input of node.inputs || []) {
        setSocketVisible(input, active.has(input.name));
    }
    for (const widget of node.widgets || []) {
        if (CONDITIONAL_WIDGETS.has(widget.name)) {
            setWidgetVisible(widget, active.has(widget.name));
        }
    }

    const editing = mode === "edit source video" || mode === "video to video";
    const countWidget = node.widgets?.find((widget) => widget.name === "count");
    if (editing && countWidget) {
        countWidget.value = 1;
    }

    if (node.flowVideoModeHelp) {
        const labels = {
            "text to video": "Prompt only",
            "start image to video": "Requires 1 start image",
            "first + last frame": "Requires start + end images",
            "ingredients / reference images": "Requires image/video references · 10 combined max",
            "edit source video": "Requires exactly 1 source video · references disabled · count fixed to 1",
            "video to video": "Requires 1 source video · optional image references · count fixed to 1",
        };
        node.flowVideoModeHelp.value = labels[mode] || "Select a video mode";
    }
    const size = node.computeSize?.();
    if (size) node.setSize([Math.max(node.size[0], 430), Math.min(size[1], 900)]);
    node.setDirtyCanvas?.(true, true);
}

function createModeHelp(node) {
    if (node.flowVideoModeHelp) return;
    node.flowVideoModeHelp = addFlowLabel(node, "flow_video_mode_help", {
        color: "#9fc8ff",
        value: "Select a video mode",
    });
}

function installModeBehavior(node) {
    createModeHelp(node);
    const modeWidget = node.widgets?.find((widget) => widget.name === "mode");
    if (modeWidget && !modeWidget.flowModeCallbackWrapped) {
        const previousCallback = modeWidget.callback;
        modeWidget.callback = function () {
            previousCallback?.apply(this, arguments);
            applyVideoMode(node);
        };
        modeWidget.flowModeCallbackWrapped = true;
    }
    queueMicrotask(() => applyVideoMode(node));
}

app.registerExtension({
    name: "comfyui-flow-agent.video-mode-inputs",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "FlowOmniFlashVideo") return;

        const previousCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            previousCreated?.apply(this, arguments);
            installModeBehavior(this);
        };

        const previousConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            previousConfigure?.apply(this, arguments);
            installModeBehavior(this);
        };
    },
});
