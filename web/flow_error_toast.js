import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

function friendlyFlowError(message) {
    if (message.includes("SPEECH_EDIT_BLOCKED") || message.includes("PUBLIC_ERROR_SPEECH_EDIT")) {
        return "Google Flow blocked speech editing. Connect the local VIDEO input so Flow Agent can upload a temporary copy without audio.";
    }
    if (message.includes("Empty response from upload")) {
        return "Flow did not accept the uploaded media. Confirm Flow Agent and its browser extension are connected, then retry.";
    }
    if (message.includes("MEDIA_GENERATION_STATUS_FAILED")) {
        return "Google Flow accepted the inputs but the generation failed remotely. Open Flow history for its detailed reason.";
    }
    return message;
}

app.registerExtension({
    name: "comfyui-flow-agent.friendly-errors",
    async setup() {
        api.addEventListener("execution_error", ({ detail }) => {
            if (detail?.node_type !== "FlowOmniFlashVideo") return;
            const message = friendlyFlowError(String(detail.exception_message || "Flow video failed."));
            app.extensionManager?.toast?.add({
                severity: "error",
                summary: "Flow / Omni Flash Video",
                detail: message,
                life: 12000,
            });
        });
    },
});
