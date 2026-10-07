// Pure helpers for the setup wizard (ADR-0026): sensible first answers.
import type { LibraryType } from '../api/libraries';
import type { LanguageOption } from '../api/titles';

const TV = /\b(tv|tv ?shows?|shows?|series|serien|séries|anime|cartoons?)\b/i;
const MOVIES = /\b(movies?|films?|filme|cinema|4k|uhd)\b/i;

/** A library name and type from the folder the user picked ("Media/TV Shows" → TV). */
export function guessLibrary(path: string): { name: string; type: LibraryType } {
  const parts = path.split('/').filter(Boolean);
  const last = parts.at(-1) ?? '';
  const name = last ? last.charAt(0).toUpperCase() + last.slice(1) : 'Media';
  const type: LibraryType = TV.test(last)
    ? 'tv'
    : MOVIES.test(last)
      ? 'movies'
      : TV.test(path)
        ? 'tv'
        : MOVIES.test(path)
          ? 'movies'
          : 'other';
  return { name: name.slice(0, 100), type };
}

/** The user's language from the browser ("de-AT" → German), else English. */
export function browserLanguage(languages: LanguageOption[], preferred: readonly string[]): string {
  for (const tag of preferred) {
    const alpha2 = tag.toLowerCase().split('-')[0];
    const match = languages.find((l) => l.alpha2 === alpha2);
    if (match) return match.code;
  }
  return 'eng';
}
