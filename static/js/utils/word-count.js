function countWords(text) {
  const chinese = (text || '').match(/[\u4e00-\u9fff]/g);
  const chineseCount = chinese ? chinese.length : 0;
  const total = (text || '').replace(/\s/g, '').length;
  return { chinese: chineseCount, total };
}
