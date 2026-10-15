// 文档工作室：从 Markdown 提取标题目录（大纲）
// 当前用正则构建大纲；需要精确定位时可改为读取编辑器状态。

export interface HeadingInfo {
  level: number; // 1-6
  text: string;
  line: number; // 从 0 开始的行号
}

export function extractHeadings(markdown: string): HeadingInfo[] {
  const headings: HeadingInfo[] = [];
  const lines = markdown.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const match = /^(#{1,6})\s+(.+?)\s*$/.exec(lines[i]);
    if (match) {
      headings.push({
        level: match[1].length,
        text: match[2],
        line: i,
      });
    }
  }
  return headings;
}
