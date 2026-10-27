/** A pure playback clock: sim time advanced by wall time times speed. Callers pass `now` in ms. */

export const MIN_SPEED = 0.1;
export const MAX_SPEED = 4;
export const DEFAULT_SPEED = 1;

/** Clamp a playback speed to [0.1, 4]; NaN becomes 1, infinities clamp to the nearer end. */
export function clampSpeed(speed: number): number {
  if (Number.isNaN(speed)) return DEFAULT_SPEED;
  return Math.min(Math.max(speed, MIN_SPEED), MAX_SPEED);
}

/**
 * Sim-time playback over `[start, end]` seconds.
 *
 * While playing, `time = anchorTime + (now - anchorNow) / 1000 * speed`; every mutation
 * re-anchors at the `now` it is given, so changing speed or seeking never jumps. Playback
 * stops (does not loop) when it reaches `end`; `play()` at the end restarts from `start`.
 * A `now` earlier than the anchor never moves time backwards.
 */
export class PlaybackClock {
  readonly start: number;
  readonly end: number;

  private current: number;
  private running = false;
  private rate = DEFAULT_SPEED;
  private anchorNow = 0;
  private anchorTime: number;

  constructor(start: number, end: number) {
    if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
      throw new RangeError(`invalid playback range ${start}..${end}`);
    }
    this.start = start;
    this.end = end;
    this.current = start;
    this.anchorTime = start;
  }

  /** Sim seconds as of the last `tick` or mutation. */
  get time(): number {
    return this.current;
  }

  get playing(): boolean {
    return this.running;
  }

  get speed(): number {
    return this.rate;
  }

  /** True once time has reached `end`. */
  get ended(): boolean {
    return this.current >= this.end;
  }

  /** Start playing from the current time, or from `start` if already at the end. */
  play(now: number): void {
    if (this.running) return;
    if (this.ended) this.current = this.start;
    // A zero-length run has nothing to play.
    if (this.end === this.start) return;
    this.running = true;
    this.anchor(now);
  }

  /** Stop at the time reached by `now`. */
  pause(now: number): void {
    if (!this.running) return;
    this.tick(now);
    this.running = false;
  }

  toggle(now: number): void {
    if (this.running) this.pause(now);
    else this.play(now);
  }

  /** Jump to `t`, clamped to `[start, end]` (NaN goes to `start`); keeps playing if it was. */
  seek(t: number, now: number): number {
    this.current = Number.isNaN(t) ? this.start : Math.min(Math.max(t, this.start), this.end);
    this.anchor(now);
    if (this.running && this.ended) this.running = false;
    return this.current;
  }

  /** Back to `start`, keeping the play/pause state. */
  restart(now: number): void {
    this.seek(this.start, now);
  }

  /** Set the speed (clamped, see `clampSpeed`) without moving the current time; returns it. */
  setSpeed(speed: number, now: number): number {
    this.tick(now);
    this.rate = clampSpeed(speed);
    this.anchor(now);
    return this.rate;
  }

  /** Advance to `now`; returns the sim time and stops at `end`. */
  tick(now: number): number {
    if (!this.running) return this.current;
    // A clock that went backwards re-anchors at the time already reached instead of rewinding.
    if (now < this.anchorNow) {
      this.anchor(now);
      return this.current;
    }
    const t = Math.max(this.current, this.anchorTime + ((now - this.anchorNow) / 1000) * this.rate);
    if (t >= this.end) {
      this.current = this.end;
      this.running = false;
    } else {
      this.current = t;
    }
    return this.current;
  }

  private anchor(now: number): void {
    this.anchorNow = now;
    this.anchorTime = this.current;
  }
}
