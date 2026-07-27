function countWords(text) {
  const chinese = (text || '').match(/[一-鿿〇]/g);
  const chineseCount = chinese ? chinese.length : 0;
  const total = (text || '').replace(/\s/g, '').length;
  return { chinese: chineseCount, total };
}
