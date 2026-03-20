// Image modal - click preview image to view full-size
document.addEventListener('DOMContentLoaded', function () {
    const previewImg = document.querySelector('.preview-img');
    if (!previewImg) return;

    // Create modal elements
    const overlay = document.createElement('div');
    overlay.id = 'imageModalOverlay';
    overlay.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:1000;cursor:zoom-out;align-items:center;justify-content:center;';

    const modalImg = document.createElement('img');
    modalImg.style.cssText = 'max-width:90vw;max-height:90vh;border-radius:8px;box-shadow:0 4px 32px rgba(0,0,0,0.5);';

    overlay.appendChild(modalImg);
    document.body.appendChild(overlay);

    previewImg.style.cursor = 'zoom-in';
    previewImg.addEventListener('click', function () {
        modalImg.src = previewImg.src;
        overlay.style.display = 'flex';
    });

    overlay.addEventListener('click', function () {
        overlay.style.display = 'none';
    });
});
