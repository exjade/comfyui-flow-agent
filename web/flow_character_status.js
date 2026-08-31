import { app } from "../../scripts/app.js";

const CHARACTER_NODES = new Set([
    "FlowCharacterCreator",
    "FlowCharacterShotSelector",
    "FlowGenerateCharacterShot",
]);

function parsePayload(value) {
    const raw = Array.isArray(value) ? value[0] : value;
    if (!raw) return null;
    if (typeof raw === "object") return raw;
    try {
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

function shortId(value) {
    if (!value) return "—";
    return value.length > 18 ? `${value.slice(0, 15)}…` : value;
}

function createStatus(node) {
    if (node.flowCharacterStatus) return node.flowCharacterStatus;

    const container = document.createElement("div");
    container.style.display = "none";
    container.style.flexDirection = "column";
    container.style.gap = "6px";
    container.style.padding = "8px";
    container.style.boxSizing = "border-box";
    container.style.background = "#111";
    container.style.border = "1px solid #333";
    container.style.borderRadius = "8px";
    container.style.fontSize = "11px";
    container.style.color = "#ddd";

    const heading = document.createElement("div");
    heading.style.fontWeight = "700";
    heading.style.color = "#fff";

    const details = document.createElement("div");
    details.style.color = "#aaa";

    const list = document.createElement("div");
    list.style.display = "flex";
    list.style.flexDirection = "column";
    list.style.gap = "3px";
    list.style.maxHeight = "250px";
    list.style.overflowY = "auto";

    container.append(heading, details, list);
    const widget = node.addDOMWidget("flow_character_status", "character_status", container, {
        hideOnZoom: false,
        getMinHeight: () => (container.style.display === "none" ? 0 : 90),
        getMaxHeight: () => 360,
    });
    widget.serialize = false;
    node.flowCharacterStatus = { container, heading, details, list, widget };
    return node.flowCharacterStatus;
}

function addCopyRow(list, record) {
    const failed = record.status === "failed";
    const row = document.createElement("button");
    row.type = "button";
    row.style.display = "grid";
    row.style.gridTemplateColumns = "34px 1fr auto";
    row.style.gap = "6px";
    row.style.alignItems = "center";
    row.style.padding = "4px 6px";
    row.style.border = "0";
    row.style.borderRadius = "4px";
    row.style.background = failed ? "#351b1b" : "#1d1d1d";
    row.style.color = failed ? "#ff9d9d" : "#ddd";
    row.style.textAlign = "left";
    row.style.cursor = "copy";
    row.title = failed
        ? (record.error || "Generation failed. Click to copy the error.")
        : "Click to copy shot ID and media ID";
    const number = document.createElement("span");
    number.textContent = `#${String(record.shot_number ?? 1).padStart(2, "0")}`;
    const shotId = document.createElement("span");
    shotId.textContent = record.shot_id || "unknown";
    const mediaId = document.createElement("span");
    mediaId.textContent = failed ? "ERROR" : shortId(record.media_id);
    row.append(number, shotId, mediaId);
    if (failed && record.error) {
        const error = document.createElement("span");
        error.textContent = record.error;
        error.style.gridColumn = "2 / 4";
        error.style.fontSize = "10px";
        error.style.lineHeight = "1.25";
        error.style.whiteSpace = "normal";
        error.style.opacity = "0.9";
        row.append(error);
    }
    row.addEventListener("click", async () => {
        const value = failed
            ? (record.error || `${record.shot_id || ""}\tfailed`)
            : `${record.shot_id || ""}\t${record.media_id || ""}`;
        try {
            await navigator.clipboard.writeText(value);
            row.title = "Copied";
        } catch {
            row.title = value;
        }
    });
    list.append(row);
}

function showStatus(node, message) {
    const dataset = parsePayload(message?.character_dataset);
    const shot = parsePayload(message?.character_shot);
    const payload = dataset || shot;
    if (!payload) return;

    const status = createStatus(node);
    status.container.style.display = "flex";
    status.list.replaceChildren();

    if (dataset) {
        status.heading.textContent = `Dataset: ${dataset.dataset_id || "unknown"}`;
        status.details.textContent = `${dataset.successful_shots ?? 0}/${dataset.requested_shots ?? 0} generated`
            + (dataset.failed_shots ? ` · ${dataset.failed_shots} failed` : "");
        for (const record of dataset.shots || []) addCopyRow(status.list, record);
    } else {
        status.heading.textContent = `Shot: ${shot.shot_id || "unknown"}`;
        status.details.textContent = `Dataset ${shot.dataset_id || "unknown"} · media ${shortId(shot.media_id)}`;
        addCopyRow(status.list, shot);
    }

    const computed = node.computeSize?.() || node.size;
    node.setSize([Math.max(node.size[0], 430), Math.max(node.size[1], computed[1])]);
    node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: "comfyui-flow-agent.character-status",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!CHARACTER_NODES.has(nodeData.name)) return;
        const previousExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            previousExecuted?.apply(this, arguments);
            showStatus(this, message);
        };
    },
});
