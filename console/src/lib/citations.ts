/** Turn "[2]" into a citation link that AnswerText renders as a chip. */
export function linkCitations(text: string): string {
  return text.replace(/\[(\d{1,2})\](?!\()/g, '[[$1]](#cite-$1)')
}
