import { fetchGroupAnnotations, $imports } from '../fetch-group-annotations';

describe('fetch-group-annotations', () => {
  let fakeCallAPI;

  beforeEach(() => {
    fakeCallAPI = sinon.stub().resolves({
      data: [],
      meta: {
        page: { total: 0 },
      },
    });

    $imports.$mock({
      '.': {
        callAPI: fakeCallAPI,
      },
    });
  });

  [
    {
      pageNumber: 10,
      pageSize: 20,
      moderationStatus: 'APPROVED',
      expectedQuery: {
        'page[number]': 10,
        'page[size]': 20,
        moderation_status: 'APPROVED',
      },
    },
    {
      moderationStatus: 'SPAM',
      expectedQuery: {
        'page[number]': 1,
        'page[size]': 20,
        moderation_status: 'SPAM',
      },
    },
    {
      pageNumber: 5,
      pageSize: 6,
      expectedQuery: {
        'page[number]': 5,
        'page[size]': 6,
      },
    },
    {
      expectedQuery: {
        'page[number]': 1,
        'page[size]': 20,
      },
    },
  ].forEach(
    ({ pageNumber = 1, pageSize = 20, moderationStatus, expectedQuery }) => {
      it('calls API with expected parameters', async () => {
        const { signal } = new AbortController();

        await fetchGroupAnnotations(
          {
            url: '/api/groups/abc123/annotations',
            method: 'GET',
            headers: {},
          },
          { signal, pageNumber, pageSize, moderationStatus },
        );

        assert.calledWith(fakeCallAPI, '/api/groups/abc123/annotations', {
          signal,
          query: expectedQuery,
          method: 'GET',
          headers: {},
        });
      });
    },
  );
});
