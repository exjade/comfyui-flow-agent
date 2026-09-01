import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_NAME = "FlowVideoLibrary";

function selectedWidget(node) {
    return node.widgets?.find((widget) => widget.name === "selected_media_id");
}

function hidePersistenceWidget(widget) {
    if (!widget || widget.flowLibraryHidden) {
        return;
    }
    widget.type = "hidden";
    widget.computeSize = () => [0, -4];
    widget.flowLibraryHidden = true;
}

function formatDate(timestamp) {
    if (!timestamp) {
        return "Unknown date";
    }
    return new Date(Number(timestamp) * 1000).toLocaleString();
}

function optionLabel(item) {
    const prompt = String(item.prompt || "Untitled video").replace(/\s+/g, " ").trim();
    const shortPrompt = prompt.length > 58 ? `${prompt.slice(0, 55)}…` : prompt;
    return `${formatDate(item.timestamp)} · ${shortPrompt}`;
}

function createLibrary(node) {
    if (node.flowVideoLibrary) {
        return node.flowVideoLibrary;
    }

    const persistence = selectedWidget(node);
    hidePersistenceWidget(persistence);

    const root = document.createElement("div");
    root.style.boxSizing = "border-box";
    root.style.width = "100%";
    root.style.padding = "8px";
    root.style.display = "flex";
    root.style.flexDirection = "column";
    root.style.gap = "7px";
    root.style.background = "#181818";
    root.style.borderRadius = "8px";

    const toolbar = document.createElement("div");
    toolbar.style.display = "grid";
    toolbar.style.gridTemplateColumns = "1fr auto";
    toolbar.style.gap = "6px";

    const filter = document.createElement("select");
    for (const [value, label] of [
        ["all", "All videos"],
        ["generated", "Generated"],
        ["uploaded", "Uploaded"],
        ["upsampled", "Upsampled"],
    ]) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        filter.append(option);
    }

    const refresh = document.createElement("button");
    refresh.type = "button";
    refresh.textContent = "Refresh videos";

    const picker = document.createElement("select");
    picker.style.width = "100%";

    const video = document.createElement("video");
    video.controls = true;
    video.preload = "metadata";
    video.playsInline = true;
    video.style.width = "100%";
    video.style.maxHeight = "340px";
    video.style.background = "#000";
    video.style.borderRadius = "6px";
    video.style.display = "none";

    const details = document.createElement("div");
    details.style.color = "#bbb";
    details.style.fontSize = "11px";
    details.textContent = "Press Refresh videos to load Flow history.";

    const open = document.createElement("a");
    open.textContent = "Open / download selected video";
    open.target = "_blank";
    open.rel = "noopener noreferrer";
    open.style.color = "#8ec5ff";
    open.style.fontSize = "12px";
    open.style.display = "none";

    toolbar.append(filter, refresh);
    root.append(toolbar, picker, video, details, open);

    const domWidget = node.addDOMWidget("flow_video_library", "library", root, {
        hideOnZoom: false,
        getMinHeight: () => 330,
        getMaxHeight: () => 520,
    });
    domWidget.serialize = false;

    const state = {
        records: [],
        root,
        filter,
        refresh,
        picker,
        video,
        details,
        open,
        persistence,
        domWidget,
    };
    node.flowVideoLibrary = state;

    function filteredRecords() {
        if (filter.value === "all") {
            return state.records;
        }
        return state.records.filter((item) => item.library_kind === filter.value);
    }

    function showSelected() {
        const mediaId = picker.value;
        const item = state.records.find((candidate) => candidate.media_id === mediaId);
        if (!item) {
            video.pause();
            video.removeAttribute("src");
            video.style.display = "none";
            open.style.display = "none";
            details.textContent = "No video selected.";
            return;
        }
        if (persistence) {
            persistence.value = item.media_id;
            persistence.callback?.(item.media_id);
        }
        video.src = item.preview_url;
        video.style.display = "block";
        video.load();
        open.href = item.preview_url;
        open.style.display = "inline";
        details.textContent = `${item.prompt || "Untitled video"} · ${formatDate(item.timestamp)} · ${item.media_id}`;
        node.setDirtyCanvas?.(true, true);
    }

    function renderOptions() {
        const previous = persistence?.value || picker.value;
        const records = filteredRecords();
        picker.replaceChildren();
        if (!records.length) {
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "No videos in this filter";
            picker.append(option);
            showSelected();
            return;
        }
        for (const item of records) {
            const option = document.createElement("option");
            option.value = item.media_id;
            option.textContent = optionLabel(item);
            picker.append(option);
        }
        picker.value = records.some((item) => item.media_id === previous)
            ? previous
            : records[0].media_id;
        showSelected();
    }

    async function loadVideos() {
        refresh.disabled = true;
        refresh.textContent = "Loading…";
        details.textContent = "Loading Flow video history…";
        try {
            const response = await api.fetchApi("/flow-agent/video-library");
            const payload = await response.json();
            if (!response.ok) {
                throw new Error(payload.error || `HTTP ${response.status}`);
            }
            state.records = Array.isArray(payload.videos) ? payload.videos : [];
            renderOptions();
        } catch (error) {
            state.records = [];
            picker.replaceChildren();
            details.textContent = `Could not load videos: ${error.message}`;
            video.style.display = "none";
            open.style.display = "none";
        } finally {
            refresh.disabled = false;
            refresh.textContent = "Refresh videos";
        }
    }

    refresh.addEventListener("click", loadVideos);
    filter.addEventListener("change", renderOptions);
    picker.addEventListener("change", showSelected);

    const previousRemoved = node.onRemoved;
    node.onRemoved = function () {
        video.pause();
        video.removeAttribute("src");
        video.load();
        previousRemoved?.apply(this, arguments);
    };

    node.setSize([Math.max(node.size[0], 460), Math.max(node.size[1], 480)]);
    queueMicrotask(loadVideos);
    return state;
}

app.registerExtension({
    name: "comfyui-flow-agent.video-library",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) {
            return;
        }

        const previousCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            previousCreated?.apply(this, arguments);
            createLibrary(this);
        };

        const previousConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            previousConfigure?.apply(this, arguments);
            queueMicrotask(() => createLibrary(this));
        };
    },
});
