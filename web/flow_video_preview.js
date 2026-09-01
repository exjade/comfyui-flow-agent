import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const FLOW_VIDEO_NODES = new Set([
    "FlowOmniFlashVideo",
]);

const VIDEO_CREDITS = {
    "720p": { 4: 7, 6: 10, 8: 12, 10: 15 },
};

function widgetValue(node, name, fallback) {
    return node.widgets?.find((widget) => widget.name === name)?.value ?? fallback;
}

function updateCreditEstimate(node) {
    const estimate = node.flowAgentCreditEstimate;
    if (!estimate) {
        return;
    }
    const resolution = String(widgetValue(node, "resolution", "720p"));
    const baseResolution = resolution === "1080p" ? "720p" : resolution;
    const duration = Number(widgetValue(node, "duration", 8));
    const count = Math.max(1, Math.min(4, Number(widgetValue(node, "count", 1)) || 1));
    const costEach = VIDEO_CREDITS[baseResolution]?.[duration];
    if (costEach == null) {
        estimate.textContent = "Costo estimado de Flow: no disponible";
        return;
    }
    const total = costEach * count;
    const upscaleNote = resolution === "1080p" ? " + upscale 1080p sin costo" : "";
    estimate.textContent = `Costo estimado de Flow: ${total} créditos (${costEach} × ${count})${upscaleNote}`;
}

function createCreditEstimate(node) {
    if (node.flowAgentCreditEstimate) {
        updateCreditEstimate(node);
        return;
    }

    const label = document.createElement("div");
    label.style.boxSizing = "border-box";
    label.style.width = "100%";
    label.style.padding = "7px 10px";
    label.style.borderRadius = "6px";
    label.style.background = "#171717";
    label.style.color = "#f0d77a";
    label.style.fontSize = "12px";
    label.style.fontWeight = "600";

    const estimateWidget = node.addDOMWidget(
        "flow_agent_credit_estimate",
        "credits",
        label,
        {
            hideOnZoom: false,
            getMinHeight: () => 32,
            getMaxHeight: () => 32,
        },
    );
    estimateWidget.serialize = false;
    node.flowAgentCreditEstimate = label;

    for (const name of ["resolution", "duration", "count"]) {
        const widget = node.widgets?.find((candidate) => candidate.name === name);
        if (!widget || widget.flowAgentCreditCallbackWrapped) {
            continue;
        }
        const previousCallback = widget.callback;
        widget.callback = function () {
            previousCallback?.apply(this, arguments);
            updateCreditEstimate(node);
        };
        widget.flowAgentCreditCallbackWrapped = true;
    }
    updateCreditEstimate(node);
}

function forceOmniSeed(node) {
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

        if (nodeData.name === "FlowOmniFlashVideo") {
            const previousCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                previousCreated?.apply(this, arguments);
                forceOmniSeed(this);
                createCreditEstimate(this);
            };

            const previousConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function () {
                previousConfigure?.apply(this, arguments);
                forceOmniSeed(this);
                createCreditEstimate(this);
                queueMicrotask(() => updateCreditEstimate(this));
            };
        }
    },
});
