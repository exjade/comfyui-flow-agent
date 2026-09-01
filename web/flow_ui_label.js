/** Small fixed-height canvas label shared by Flow Agent node extensions. */
export function addFlowLabel(node, name, { color, value = "" }) {
    const existing = node.widgets?.find((widget) => widget.name === name);
    if (existing) return existing;

    const widget = {
        name,
        type: "FLOW_AGENT_LABEL",
        value,
        options: { serialize: false },
        serialize: false,
        computeSize(width) {
            return [width, 28];
        },
        draw(ctx, _node, width, y, height) {
            const rowHeight = Math.min(26, height || 26);
            ctx.save();
            ctx.fillStyle = "#171717";
            ctx.beginPath();
            ctx.roundRect(8, y + 1, Math.max(0, width - 16), rowHeight - 2, 6);
            ctx.fill();
            ctx.fillStyle = color;
            ctx.font = "12px sans-serif";
            ctx.textBaseline = "middle";
            ctx.fillText(String(this.value || ""), 14, y + rowHeight / 2, Math.max(0, width - 28));
            ctx.restore();
        },
    };
    node.addCustomWidget(widget);
    return widget;
}
