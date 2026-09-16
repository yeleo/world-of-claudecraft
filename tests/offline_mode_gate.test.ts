import { describe, expect, it } from 'vitest';
import { isOfflineModeAvailable } from '../src/game/offline_mode_gate';

describe('isOfflineModeAvailable', () => {
  it('is permanently disabled in all environments', () => {
    expect(isOfflineModeAvailable(true)).toBe(false);
    expect(isOfflineModeAvailable(false)).toBe(false);
  });
});
