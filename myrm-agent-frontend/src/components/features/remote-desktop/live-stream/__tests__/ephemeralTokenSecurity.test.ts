import { describe, it, expect } from 'vitest';
import {
  computeSha256Digest,
  generateEphemeralShareTicket,
  verifyEphemeralShareTicket,
  formatTimeRemaining,
} from '../ephemeralTokenSecurity';
import { EphemeralShareTicket, ShareOptions } from '../remoteDesktopTypes';

describe('ephemeralTokenSecurity pure cryptographic logic', () => {
  it('computes deterministic, non-empty digest for identical input', () => {
    const inputA = 'ticket-123:sandbox-456:1700000000000:true:false:secret-salt';
    const digest1 = computeSha256Digest(inputA);
    const digest2 = computeSha256Digest(inputA);
    const digest3 = computeSha256Digest(inputA + '-modified');

    expect(digest1).toBe(digest2);
    expect(digest1.length).toBe(16);
    expect(digest1).not.toBe(digest3);
  });

  it('generates valid ephemeral share ticket with calculated expiration and signature', () => {
    const baseNow = 1700000000000;
    const options: ShareOptions = {
      ttlSeconds: 3600,
      allowTakeover: true,
      oneTimeOnly: false,
    };

    const ticket = generateEphemeralShareTicket(
      'sandbox-cloud-vm-99',
      options,
      'test-secret-salt',
      'https://myrm.ai/share/live'
    );

    expect(ticket.ticketId.startsWith('tkt-')).toBe(true);
    expect(ticket.sandboxId).toBe('sandbox-cloud-vm-99');
    expect(ticket.allowTakeover).toBe(true);
    expect(ticket.oneTimeOnly).toBe(false);
    expect(ticket.signature).toBeTruthy();
    expect(ticket.url).toContain('https://myrm.ai/share/live?t=');
    expect(ticket.url).toContain('&sb=sandbox-cloud-vm-99');
    expect(ticket.url).toContain('&tk=1');
    expect(ticket.url).toContain('&oto=0');
    expect(ticket.url).toContain(`&sig=${ticket.signature}`);
  });

  it('verifies valid tickets successfully', () => {
    const fixedNow = 1700000000000;
    const secretKey = 'myrm-test-salt';
    const options: ShareOptions = {
      ttlSeconds: 7200,
      allowTakeover: false,
      oneTimeOnly: true,
    };

    const ticket = generateEphemeralShareTicket('sb-001', options, secretKey);
    const result = verifyEphemeralShareTicket(ticket, secretKey, fixedNow);

    expect(result.valid).toBe(true);
    expect(result.reason).toBeUndefined();
  });

  it('rejects expired tickets with reason expired', () => {
    const ticket: EphemeralShareTicket = {
      ticketId: 'tkt-test-1',
      sandboxId: 'sb-001',
      expiresAt: 1700000000000,
      signature: 'any-sig',
      url: 'https://myrm.ai/share',
      allowTakeover: false,
      oneTimeOnly: false,
    };

    const result = verifyEphemeralShareTicket(ticket, 'secret', 1700000000001);
    expect(result.valid).toBe(false);
    expect(result.reason).toBe('expired');
  });

  it('rejects altered tickets with invalid-signature reason', () => {
    const secretKey = 'salt-123';
    const options: ShareOptions = {
      ttlSeconds: 3600,
      allowTakeover: false,
      oneTimeOnly: false,
    };

    const ticket = generateEphemeralShareTicket('sb-001', options, secretKey);
    const tamperedTicket: EphemeralShareTicket = {
      ...ticket,
      allowTakeover: true, // Tampered permission
    };

    const result = verifyEphemeralShareTicket(tamperedTicket, secretKey, Date.now());
    expect(result.valid).toBe(false);
    expect(result.reason).toBe('invalid-signature');
  });

  it('detects malformed tickets missing critical fields', () => {
    const malformedTicket = {
      ticketId: '',
      sandboxId: 'sb-001',
      expiresAt: 2000000000000,
      signature: 'abc',
      url: '',
      allowTakeover: false,
      oneTimeOnly: false,
    };

    const result = verifyEphemeralShareTicket(malformedTicket as EphemeralShareTicket);
    expect(result.valid).toBe(false);
    expect(result.reason).toBe('malformed');
  });

  it('formats time remaining accurately across hours, minutes and seconds', () => {
    const baseNow = 10000000;

    expect(formatTimeRemaining(baseNow - 10, baseNow)).toBe('已过期');
    expect(formatTimeRemaining(baseNow + 45 * 1000, baseNow)).toBe('45秒');
    expect(formatTimeRemaining(baseNow + (5 * 60 + 30) * 1000, baseNow)).toBe('5分30秒');
    expect(formatTimeRemaining(baseNow + (2 * 3600 + 15 * 60) * 1000, baseNow)).toBe('2小时15分');
  });
});
