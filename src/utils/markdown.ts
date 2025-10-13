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
    // Pre-process markdown: replace triple+ newlines with double newlines
    // This reduces excessive spacing while preserving paragraph structure
    let processed = markdown.replace(/\n{3,}/g, '\n\n');

    // Use synchronous parse
    const result = marked(processed);
    let html = typeof result === 'string' ? result : String(result);

    // Remove trailing whitespace and empty paragraphs at the end
    html = html.replace(/(<p>\s*<\/p>|\s)+$/g, '');

    return html;
  } catch (error) {
    console.error('Error rendering markdown:', error);
    return markdown; // Fallback to plain text
  }
}
