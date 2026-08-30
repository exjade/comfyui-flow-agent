import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const FLOW_VIDEO_NODES = new Set([
    "FlowOmniFlashVideo",
    "FlowVideoUpsample",
]);

function videoUrl(item) {
    const params = new URLSearchParams({
        filename: item.filename,
        subfolder: item.subfolder || "",
        type: item.type || "output",
        t: String(Date.now()),
    });
    return api.apiURL(`/view?${params.toString()}`);
}

function createPreview(node) {
    if (node.flowAgentVideoPreview) {
        return node.flowAgentVideoPreview;
    }

    const container = document.createElement("div");
    container.style.display = "none";
    container.style.flexDirection = "column";
    container.style.gap = "6px";
    container.style.width = "100%";
    container.style.boxSizing = "border-box";
    container.style.padding = "4px";
    container.style.background = "#111";
    container.style.borderRadius = "8px";

    const video = document.createElement("video");
    video.controls = true;
    video.preload = "metadata";
    video.playsInline = true;
    video.style.display = "block";
    video.style.width = "100%";
    video.style.maxHeight = "420px";
    video.style.background = "#000";
    video.style.borderRadius = "6px";

    const actions = document.createElement("div");
    actions.style.display = "flex";
    actions.style.justifyContent = "space-between";
    actions.style.alignItems = "center";
    actions.style.fontSize = "12px";

    const status = document.createElement("span");
    status.textContent = "Flow video";
    status.style.color = "#bbb";

    const openLink = document.createElement("a");
    openLink.textContent = "Open / download";
    openLink.target = "_blank";
    openLink.rel = "noopener noreferrer";
    openLink.style.color = "#8ec5ff";

    actions.append(status, openLink);
    container.append(video, actions);

    const widget = node.addDOMWidget(
        "flow_agent_video_preview",
        "video",
        container,
        {
            hideOnZoom: false,
            getMinHeight: () => (container.style.display === "none" ? 0 : 260),
            getMaxHeight: () => 480,
        },
    );
    // UI-only state must never be serialized into workflow widget values.
    widget.serialize = false;

    const preview = { container, video, openLink, widget };
    node.flowAgentVideoPreview = preview;

    const previousRemoved = node.onRemoved;
    node.onRemoved = function () {
        video.pause();
        video.removeAttribute("src");
        video.load();
        previousRemoved?.apply(this, arguments);
    };

    return preview;
}

function showPreview(node, message) {
    // Current ComfyUI versions render `images` with `animated` natively. Do not
    // add a second DOM video for the same file. Keep this extension only as a
    // compatibility fallback for responses that expose legacy VHS `gifs`.
    if (Array.isArray(message?.images) && message.images.some((item) => item?.filename)) {
        return;
    }
    const items = message?.gifs;
    const item = Array.isArray(items) ? items[0] : null;
    if (!item?.filename) {
        return;
    }

    const preview = createPreview(node);
    const url = videoUrl(item);
    preview.video.src = url;
    preview.openLink.href = url;
    preview.container.style.display = "flex";
    preview.video.load();

    const computed = node.computeSize?.() || node.size;
    node.setSize([
        Math.max(node.size[0], 400),
        Math.max(node.size[1], computed[1]),
    ]);
    node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: "comfyui-flow-agent.inline-video-preview",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!FLOW_VIDEO_NODES.has(nodeData.name)) {
            return;
        }

        const previousExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            previousExecuted?.apply(this, arguments);
            showPreview(this, message);
        };
    },
});
