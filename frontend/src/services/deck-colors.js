const colors = new Map();
const pastels = ['lilac','peach','mint','blue','rose','butter','aqua'];
let remainingColors = [];
export function deckColor(id) {
  if (!colors.has(id)) {
    if (!remainingColors.length) {
      remainingColors = [...pastels];
      for (let index = remainingColors.length - 1; index > 0; index--) {
        const other = Math.floor(Math.random() * (index + 1));
        [remainingColors[index], remainingColors[other]] = [remainingColors[other], remainingColors[index]];
      }
    }
    colors.set(id, remainingColors.pop());
  }
  return colors.get(id);
}
