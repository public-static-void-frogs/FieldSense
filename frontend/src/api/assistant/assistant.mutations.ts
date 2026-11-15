import { mutationOptions } from '@tanstack/react-query';
import { assistantApi } from './assistant.api.ts';

export const assistantMutations = {
  // Each call streams one answer; nothing is cached because the server keeps no chat state.
  chat: () =>
    mutationOptions({
      mutationKey: ['assistant', 'chat'],
      mutationFn: assistantApi.streamChat,
      retry: false,
    }),
};
