import { describe, expect, it } from "vitest";
import { clampSpeed, MAX_SPEED, MIN_SPEED, PlaybackClock } from "./clock";

describe("clampSpeed", () => {
  it("clamps to 0.1..4", () => {
    expect(clampSpeed(0.01)).toBe(MIN_SPEED);
    expect(clampSpeed(-3)).toBe(MIN_SPEED);
    expect(clampSpeed(100)).toBe(MAX_SPEED);
    expect(clampSpeed(2.5)).toBe(2.5);
    expect(MIN_SPEED).toBe(0.1);
    expect(MAX_SPEED).toBe(4);
  });
  it("handles NaN and infinities", () => {
    expect(clampSpeed(NaN)).toBe(1);
    expect(clampSpeed(Infinity)).toBe(4);
    expect(clampSpeed(-Infinity)).toBe(0.1);
  });
});

describe("PlaybackClock", () => {
  it("validates the range", () => {
    expect(() => new PlaybackClock(NaN, 1)).toThrow(RangeError);
    expect(() => new PlaybackClock(0, Infinity)).toThrow(RangeError);
    expect(() => new PlaybackClock(2, 1)).toThrow(RangeError);
    expect(() => new PlaybackClock(0, 0)).not.toThrow();
  });

  it("starts paused at the start", () => {
    const c = new PlaybackClock(1, 5);
    expect(c.time).toBe(1);
    expect(c.playing).toBe(false);
    expect(c.speed).toBe(1);
    expect(c.tick(10_000)).toBe(1);
  });

  it("advances by wall delta times speed", () => {
    const c = new PlaybackClock(0, 100);
    c.play(1000);
    expect(c.tick(1500)).toBeCloseTo(0.5);
    c.setSpeed(2, 1500);
    expect(c.tick(2500)).toBeCloseTo(2.5);
  });

  it("changing speed mid-play does not jump time", () => {
    const c = new PlaybackClock(0, 100);
    c.play(0);
    c.tick(2000);
    c.setSpeed(4, 2000);
    expect(c.time).toBeCloseTo(2);
    c.setSpeed(0.1, 3000);
    expect(c.time).toBeCloseTo(6);
    expect(c.tick(4000)).toBeCloseTo(6.1);
  });

  it("setSpeed returns the clamped value", () => {
    const c = new PlaybackClock(0, 10);
    expect(c.setSpeed(99, 0)).toBe(4);
    expect(c.setSpeed(NaN, 0)).toBe(1);
    expect(c.setSpeed(-Infinity, 0)).toBe(0.1);
    expect(c.speed).toBe(0.1);
  });

  it("pause freezes time", () => {
    const c = new PlaybackClock(0, 10);
    c.play(0);
    c.pause(1000);
    expect(c.time).toBeCloseTo(1);
    expect(c.playing).toBe(false);
    expect(c.tick(5000)).toBeCloseTo(1);
    c.play(6000);
    expect(c.tick(7000)).toBeCloseTo(2);
  });

  it("toggle flips play state", () => {
    const c = new PlaybackClock(0, 10);
    c.toggle(0);
    expect(c.playing).toBe(true);
    c.toggle(500);
    expect(c.playing).toBe(false);
    expect(c.time).toBeCloseTo(0.5);
  });

  it("seek clamps and keeps the play state", () => {
    const c = new PlaybackClock(1, 3);
    expect(c.seek(-5, 0)).toBe(1);
    expect(c.seek(99, 0)).toBe(3);
    expect(c.seek(NaN, 0)).toBe(1);
    expect(c.playing).toBe(false);
    c.play(0);
    c.seek(2, 100);
    expect(c.playing).toBe(true);
    expect(c.tick(600)).toBeCloseTo(2.5);
    const paused = new PlaybackClock(0, 10);
    paused.seek(4, 0);
    expect(paused.playing).toBe(false);
    expect(paused.tick(9999)).toBe(4);
  });

  it("stops at the end without looping", () => {
    const c = new PlaybackClock(0, 2);
    c.play(0);
    expect(c.tick(5000)).toBe(2);
    expect(c.playing).toBe(false);
    expect(c.ended).toBe(true);
    expect(c.tick(9000)).toBe(2);
    expect(c.time).toBe(2);
  });

  it("play at the end restarts from the start", () => {
    const c = new PlaybackClock(1, 2);
    c.play(0);
    c.tick(5000);
    c.play(6000);
    expect(c.playing).toBe(true);
    expect(c.time).toBe(1);
    expect(c.tick(6500)).toBeCloseTo(1.5);
  });

  it("restart keeps play/pause state", () => {
    const playing = new PlaybackClock(0, 10);
    playing.play(0);
    playing.tick(3000);
    playing.restart(3000);
    expect(playing.time).toBe(0);
    expect(playing.playing).toBe(true);
    expect(playing.tick(4000)).toBeCloseTo(1);

    const paused = new PlaybackClock(0, 10);
    paused.seek(5, 0);
    paused.restart(0);
    expect(paused.time).toBe(0);
    expect(paused.playing).toBe(false);
  });

  it("handles a zero-length range", () => {
    const c = new PlaybackClock(2, 2);
    c.play(0);
    expect(c.time).toBe(2);
    expect(c.tick(1000)).toBe(2);
    expect(c.playing).toBe(false);
    expect(c.seek(5, 0)).toBe(2);
  });

  it("a backwards now never rewinds time", () => {
    const c = new PlaybackClock(0, 10);
    c.play(5000);
    c.tick(6000);
    expect(c.tick(1000)).toBeCloseTo(1);
    expect(c.time).toBeGreaterThanOrEqual(1);
  });

  it("seeking onto the end stops playback", () => {
    const c = new PlaybackClock(0, 2);
    c.play(0);
    c.seek(2, 0);
    expect(c.playing).toBe(false);
    expect(c.time).toBe(2);
  });
});
