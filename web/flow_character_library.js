import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_NAME = "FlowCharacterShotSelector";

function persistenceWidget(node) {
    return node.widgets?.find((widget) => widget.name === "selection_json");
}

function hideWidget(widget) {
    if (!widget || widget.flowCharacterLibraryHidden) return;
    widget.type = "hidden";
    widget.computeSize = () => [0, -4];
    widget.flowCharacterLibraryHidden = true;
}

function previewUrl(preview) {
    const params = new URLSearchParams({
        filename: preview?.filename || "",
        subfolder: preview?.subfolder || "",
        type: preview?.type || "output",
    });
    return api.apiURL(`/view?${params.toString()}`);
}

function formatDate(timestamp) {
    return timestamp ? new Date(timestamp * 1000).toLocaleString() : "Unknown date";
}

function createLibrary(node) {
    if (node.flowCharacterLibrary) return node.flowCharacterLibrary;
    const persistence = persistenceWidget(node);
    hideWidget(persistence);

    const root = document.createElement("div");
    Object.assign(root.style, {
        width: "100%", boxSizing: "border-box", padding: "8px", display: "flex",
        flexDirection: "column", gap: "7px", background: "#181818", borderRadius: "8px",
    });
    const toolbar = document.createElement("div");
    Object.assign(toolbar.style, { display: "grid", gridTemplateColumns: "1fr auto", gap: "6px" });
    const datasetPicker = document.createElement("select");
    const refresh = document.createElement("button");
    refresh.type = "button";
    refresh.textContent = "Refresh datasets";
    toolbar.append(datasetPicker, refresh);

    const shotPicker = document.createElement("select");
    const image = document.createElement("img");
    Object.assign(image.style, {
        width: "100%", maxHeight: "420px", objectFit: "contain", background: "#111",
        borderRadius: "6px", display: "none",
    });
    const details = document.createElement("div");
    Object.assign(details.style, { color: "#bbb", fontSize: "11px" });
    details.textContent = "Press Refresh datasets to load saved Character Creator results.";
    root.append(toolbar, shotPicker, image, details);

    const domWidget = node.addDOMWidget("flow_character_library", "library", root, {
        hideOnZoom: false,
        getMinHeight: () => 360,
        getMaxHeight: () => 590,
    });
    domWidget.serialize = false;
    const state = { datasets: [], persistence, datasetPicker, shotPicker, image, details };
    node.flowCharacterLibrary = state;

    function currentDataset() {
        return state.datasets.find((item) => item.dataset_id === datasetPicker.value);
    }

    function showShot() {
        const dataset = currentDataset();
        const shotNumber = Number(shotPicker.value || 0);
        const shot = dataset?.shots?.find((item) => Number(item.shot_number) === shotNumber);
        if (!dataset || !shot) {
            image.removeAttribute("src");
            image.style.display = "none";
            details.textContent = "No saved shot selected.";
            return;
        }
        const selection = JSON.stringify({ dataset_id: dataset.dataset_id, shot_number: shot.shot_number });
        if (persistence) {
            persistence.value = selection;
            persistence.callback?.(selection);
        }
        image.src = previewUrl(shot.preview);
        image.style.display = "block";
        details.textContent = `#${shot.shot_number} ${shot.shot_id} · ${shot.media_id || "no media ID"}`;
        node.setDirtyCanvas?.(true, true);
    }

    function renderShots() {
        const dataset = currentDataset();
        shotPicker.replaceChildren();
        for (const shot of dataset?.shots || []) {
            const option = document.createElement("option");
            option.value = String(shot.shot_number);
            option.textContent = `#${shot.shot_number} · ${shot.shot_id}`;
            shotPicker.append(option);
        }
        try {
            const saved = JSON.parse(persistence?.value || "{}");
            if (saved.dataset_id === dataset?.dataset_id) shotPicker.value = String(saved.shot_number || "");
        } catch {}
        showShot();
    }

    function renderDatasets() {
        datasetPicker.replaceChildren();
        for (const dataset of state.datasets) {
            const option = document.createElement("option");
            option.value = dataset.dataset_id;
            option.textContent = `${formatDate(dataset.created_at)} · ${dataset.subject_description} (${dataset.shot_count})`;
            datasetPicker.append(option);
        }
        try {
            const saved = JSON.parse(persistence?.value || "{}");
            if (state.datasets.some((item) => item.dataset_id === saved.dataset_id)) {
                datasetPicker.value = saved.dataset_id;
            }
        } catch {}
        renderShots();
    }

    async function loadDatasets() {
        refresh.disabled = true;
        refresh.textContent = "Loading…";
        try {
            const response = await api.fetchApi("/flow-agent/character-library");
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
            state.datasets = Array.isArray(payload.datasets) ? payload.datasets : [];
            renderDatasets();
            if (!state.datasets.length) {
                details.textContent = "No saved datasets yet. Run Character Creator once.";
            }
        } catch (error) {
            state.datasets = [];
            datasetPicker.replaceChildren();
            shotPicker.replaceChildren();
            image.style.display = "none";
            details.textContent = `Could not load datasets: ${error.message}`;
        } finally {
            refresh.disabled = false;
            refresh.textContent = "Refresh datasets";
        }
    }

    refresh.addEventListener("click", loadDatasets);
    datasetPicker.addEventListener("change", renderShots);
    shotPicker.addEventListener("change", showShot);
    node.setSize([Math.max(node.size[0], 460), Math.max(node.size[1], 520)]);
    queueMicrotask(loadDatasets);
    return state;
}

app.registerExtension({
    name: "comfyui-flow-agent.character-library",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) return;
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
