import {MAX_IMAGE_BYTES,safeImageUrl} from '../../js/card-content.js';

export async function readPhoto(file) {
  if (!['image/png','image/jpeg','image/webp'].includes(file.type)) throw new Error('Choose a PNG, JPG, or WebP photo.');
  if (file.size > MAX_IMAGE_BYTES) throw new Error('Choose a photo smaller than 1.5 MB.');
  const source = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('This photo could not be read. Try another image.'));
    reader.readAsDataURL(file);
  });
  if (!safeImageUrl(source)) throw new Error('This photo could not be read. Try another image.');
  const photo = new Image();
  photo.src = source;
  try { await photo.decode(); } catch { throw new Error('This file is not a readable photo.'); }
  if (photo.naturalWidth * photo.naturalHeight > 16000000) throw new Error('Choose a photo no larger than 16 megapixels.');
  return source;
}
