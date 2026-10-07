import { browserLanguage, guessLibrary } from './guess';

it('guesses a library from its folder', () => {
  expect(guessLibrary('TV')).toEqual({ name: 'TV', type: 'tv' });
  expect(guessLibrary('Media/TV Shows')).toEqual({ name: 'TV Shows', type: 'tv' });
  expect(guessLibrary('series')).toEqual({ name: 'Series', type: 'tv' });
  expect(guessLibrary('Movies 4K')).toEqual({ name: 'Movies 4K', type: 'movies' });
  expect(guessLibrary('films/')).toEqual({ name: 'Films', type: 'movies' });
  expect(guessLibrary('Movies/Anime')).toEqual({ name: 'Anime', type: 'tv' }); // the folder wins
  expect(guessLibrary('Home videos')).toEqual({ name: 'Home videos', type: 'other' });
  expect(guessLibrary('')).toEqual({ name: 'Media', type: 'other' });
});

it('picks the browser language', () => {
  const languages = [
    { code: 'eng', name: 'English', alpha2: 'en' },
    { code: 'deu', name: 'German', alpha2: 'de' },
  ];
  expect(browserLanguage(languages, ['de-AT', 'en'])).toBe('deu');
  expect(browserLanguage(languages, ['xx', 'en-GB'])).toBe('eng');
  expect(browserLanguage(languages, [])).toBe('eng');
});
