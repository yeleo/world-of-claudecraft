import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  DESKTOP_VERSION,
  desktopDownloadUrl,
  detectDesktopPlatform,
} from '../src/game/desktop_download';

// Real userAgent strings (trimmed) for the desktop and mobile families.
const UA = {
  mac: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15',
  win: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36',
  winArm: 'Mozilla/5.0 (Windows NT 10.0; ARM64; WoA) AppleWebKit/537.36 Chrome/125 Safari/537.36',
  linux: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36',
  linuxArm: 'Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 Chrome/125 Safari/537.36',
  fedoraAtomic: 'Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0',
  android:
    'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/125 Mobile Safari/537.36',
  iphone:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1',
};

describe('DESKTOP_VERSION', () => {
  it('equals the package.json version, so a release bump can never leave it stale', () => {
    const pkg = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
    expect(DESKTOP_VERSION).toBe(pkg.version);
  });

  it('is a real version, not the no-define fallback', () => {
    expect(DESKTOP_VERSION).not.toBe('0.0.0');
    expect(DESKTOP_VERSION).toMatch(/^\d+\.\d+\.\d+$/);
  });
});

describe('detectDesktopPlatform', () => {
  it('detects macOS', () => {
    expect(detectDesktopPlatform(UA.mac)).toBe('mac');
  });

  it('detects Windows (x64 and arm64)', () => {
    expect(detectDesktopPlatform(UA.win)).toBe('win');
    expect(detectDesktopPlatform(UA.winArm)).toBe('win-arm64');
  });

  it('detects Linux (x86_64 and arm64), including Fedora atomic (Bazzite) UAs', () => {
    expect(detectDesktopPlatform(UA.linux)).toBe('linux');
    expect(detectDesktopPlatform(UA.fedoraAtomic)).toBe('linux');
    expect(detectDesktopPlatform(UA.linuxArm)).toBe('linux-arm64');
  });

  it('does not treat Android as a Linux desktop', () => {
    expect(detectDesktopPlatform(UA.android)).toBe('android');
  });

  it('maps iOS (reports "Mac") to mac, and unknowns to other', () => {
    expect(detectDesktopPlatform(UA.iphone)).toBe('mac');
    expect(detectDesktopPlatform('some-unknown-agent')).toBe('other');
  });
});

describe('desktopDownloadUrl', () => {
  it('builds the Android APK URL', () => {
    expect(desktopDownloadUrl('android')).toBe(
      `https://worldofclaudecraft.aoruantech.com/releases/download/v${DESKTOP_VERSION}-cn/world-of-claudecraft-${DESKTOP_VERSION}-android.apk`,
    );
  });

  it('builds the Linux x86_64 AppImage URL (electron-builder x64 arch token)', () => {
    expect(desktopDownloadUrl('linux')).toBe(
      `https://worldofclaudecraft.aoruantech.com/releases/download/v${DESKTOP_VERSION}-cn/world-of-claudecraft-${DESKTOP_VERSION}-linux-x86_64.AppImage`,
    );
    expect(desktopDownloadUrl('linux-x86_64')).toBe(
      `https://worldofclaudecraft.aoruantech.com/releases/download/v${DESKTOP_VERSION}-cn/world-of-claudecraft-${DESKTOP_VERSION}-linux-x86_64.AppImage`,
    );
  });

  it('builds the Linux ARM64 AppImage URL', () => {
    expect(desktopDownloadUrl('linux-arm64')).toBe(
      `https://worldofclaudecraft.aoruantech.com/releases/download/v${DESKTOP_VERSION}-cn/world-of-claudecraft-${DESKTOP_VERSION}-linux-arm64.AppImage`,
    );
  });

  it('builds the x64 Windows NSIS installer URL', () => {
    expect(desktopDownloadUrl('win')).toBe(
      `https://worldofclaudecraft.aoruantech.com/releases/download/v${DESKTOP_VERSION}-cn/world-of-claudecraft-${DESKTOP_VERSION}-win-x64.exe`,
    );
    expect(desktopDownloadUrl('win-x64')).toBe(
      `https://worldofclaudecraft.aoruantech.com/releases/download/v${DESKTOP_VERSION}-cn/world-of-claudecraft-${DESKTOP_VERSION}-win-x64.exe`,
    );
  });

  it('builds the ARM64 Windows NSIS installer URL', () => {
    expect(desktopDownloadUrl('win-arm64')).toBe(
      `https://worldofclaudecraft.aoruantech.com/releases/download/v${DESKTOP_VERSION}-cn/world-of-claudecraft-${DESKTOP_VERSION}-win-arm64.exe`,
    );
  });

  it('returns null for platforms with no published artifact', () => {
    expect(desktopDownloadUrl('mac')).toBeNull();
    expect(desktopDownloadUrl('other')).toBeNull();
  });
});
