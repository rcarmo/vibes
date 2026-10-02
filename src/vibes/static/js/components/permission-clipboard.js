// Preserve exact command bytes, including on trusted-LAN HTTP (no Clipboard API).
export async function copyPermissionText(text, container) {
    if (navigator.clipboard?.writeText) {
        try { await navigator.clipboard.writeText(text); return true; } catch { /* HTTP/permission fallback */ }
    }
    const previous = document.activeElement;
    const area = document.createElement('textarea');
    area.value = text;
    area.readOnly = true;
    area.style.cssText = 'position:fixed;left:-10000px;top:0;opacity:0';
    (container || document.body).appendChild(area);
    try {
        area.select();
        area.setSelectionRange(0, text.length);
        return document.execCommand('copy');
    } finally {
        area.remove();
        previous?.focus?.({ preventScroll: true });
    }
}
