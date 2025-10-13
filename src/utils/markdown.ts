// Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
// SPDX-License-Identifier: BSD-3-Clause

/**
 * Markdown rendering utilities
 */

import { marked } from 'marked';

// Configure marked for safe rendering
// Valid options: async, breaks, gfm, pedantic, renderer, silent, tokenizer, walkTokens
marked.setOptions({
  breaks: false, // Disable automatic line breaks to reduce blank lines
  gfm: true // GitHub Flavored Markdown
});

/**
 * Render markdown text to HTML
 * @param markdown - The markdown text to render
 * @returns HTML string
 */
export function renderMarkdown(markdown: string): string {
  if (!markdown) {
    return '';
  }

  try {
    // Pre-process markdown: replace all double+ newlines with single newlines
    // This eliminates excessive spacing between sections
    let processed = markdown.replace(/\n\n+/g, '\n');

    console.log('=== MARKDOWN RENDERING DEBUG ===');
    console.log('Original markdown:', markdown.substring(0, 500));
    console.log('Processed markdown:', processed.substring(0, 500));

    // Use synchronous parse
    const result = marked(processed);
    let html = typeof result === 'string' ? result : String(result);

    console.log('Generated HTML:', html.substring(0, 500));

    // Remove trailing whitespace and empty paragraphs at the end
    html = html.replace(/(<p>\s*<\/p>|\s)+$/g, '');

    console.log('Final HTML:', html.substring(0, 500));
    console.log('=== END DEBUG ===');

    return html;
  } catch (error) {
    console.error('Error rendering markdown:', error);
    return markdown; // Fallback to plain text
  }
}
