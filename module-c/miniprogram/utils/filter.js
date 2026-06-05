/**
 * 按用户标签过滤简报内容 — index / detail 页面公用
 */
function filterByTags(briefing, userTags) {
  if (!userTags || userTags.length === 0) return briefing;
  const tagSet = new Set(userTags);
  const filteredSections = [];
  for (const section of briefing.sections || []) {
    const matched = (section.items || []).filter(item =>
      (item.tags || []).some(t => tagSet.has(t))
    );
    if (matched.length > 0) {
      filteredSections.push({ ...section, items: matched });
    }
  }
  if (filteredSections.length === 0) return briefing;
  return { ...briefing, sections: filteredSections };
}

module.exports = { filterByTags };
