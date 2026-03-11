"use client";

import { cn } from "@/lib/utils";
import {
  motion,
  useAnimationFrame,
  useMotionTemplate,
  useMotionValue,
  useSpring,
  useTransform,
  MotionValue,
} from "motion/react";
import { useEffect, useRef } from "react";

const BASE_TRAVEL_DIAGONAL = Math.hypot(220, 56);
const COLLISION_EPSILON = 0.9;
const COLLISION_COOLDOWN_MS = 72;

function getTravelScale(width: number, height: number): number {
  const diagonal = Math.hypot(Math.max(width, 1), Math.max(height, 1));
  return Math.max(1, diagonal / BASE_TRAVEL_DIAGONAL);
}

function getEdgePadding(width: number, height: number): number {
  const minSide = Math.min(width, height);
  return Math.min(24, Math.max(10, minSide * 0.24));
}

// Helper component for gradient layers
function GradientLayer({
  springX,
  springY,
  gradientColor,
  opacity,
  multiplier,
}: {
  springX: MotionValue<number>;
  springY: MotionValue<number>;
  gradientColor: string;
  opacity: number;
  multiplier: number;
}) {
  const x = useTransform(springX, (val) => val * multiplier);
  const y = useTransform(springY, (val) => val * multiplier);
  const background = useMotionTemplate`radial-gradient(circle at ${x}px ${y}px, ${gradientColor} 0%, transparent 50%)`;

  return (
    <motion.div
      className="absolute inset-0"
      style={{
        opacity,
        background,
      }}
    />
  );
}

interface NoiseBackgroundProps {
  children?: React.ReactNode;
  className?: string;
  containerClassName?: string;
  gradientColors?: string[];
  noiseIntensity?: number;
  speed?: number;
  backdropBlur?: boolean;
  animating?: boolean;
}

export const NoiseBackground = ({
  children,
  className,
  containerClassName,
  gradientColors = [
    "rgb(255, 100, 150)",
    "rgb(100, 150, 255)",
    "rgb(255, 200, 100)",
  ],
  noiseIntensity = 0.12,
  speed = 0.1,
  backdropBlur = false,
  animating = true,
}: NoiseBackgroundProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);

  // Use spring animation for smooth movement
  const springX = useSpring(x, { stiffness: 100, damping: 30 });
  const springY = useSpring(y, { stiffness: 100, damping: 30 });

  // Transform for top gradient strip
  const topGradientX = useTransform(springX, (val) => val * 0.1 - 50);

  const velocityRef = useRef({ x: 0, y: 0 });
  const lastDirectionChangeRef = useRef(0);
  const lastCollisionTimeRef = useRef(0);
  const lastFrameTimeRef = useRef<number | null>(null);

  // Initialize position to center
  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;
    const rect = container.getBoundingClientRect();
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    x.set(centerX);
    y.set(centerY);
  }, [x, y]);

  // Generate random velocity
  const generateRandomVelocityRef = useRef((travelScale = 1) => {
    const angle = Math.random() * Math.PI * 2;
    const magnitude = speed * travelScale * (0.5 + Math.random() * 0.5); // Keep flow intensity when container grows
    return {
      x: Math.cos(angle) * magnitude,
      y: Math.sin(angle) * magnitude,
    };
  });

  // Update generateRandomVelocity when speed changes
  useEffect(() => {
    generateRandomVelocityRef.current = (travelScale = 1) => {
      const angle = Math.random() * Math.PI * 2;
      const magnitude = speed * travelScale * (0.5 + Math.random() * 0.5);
      return {
        x: Math.cos(angle) * magnitude,
        y: Math.sin(angle) * magnitude,
      };
    };
    const rect = containerRef.current?.getBoundingClientRect();
    const travelScale = rect ? getTravelScale(rect.width, rect.height) : 1;
    velocityRef.current = generateRandomVelocityRef.current(travelScale);
  }, [speed]);

  // Animate using motion/react's useAnimationFrame
  useAnimationFrame((time) => {
    if (!animating || !containerRef.current) {
      lastFrameTimeRef.current = null;
      return;
    }

    const rect = containerRef.current.getBoundingClientRect();
    const maxX = Math.max(rect.width, 1);
    const maxY = Math.max(rect.height, 1);
    const travelScale = getTravelScale(maxX, maxY);
    const padding = getEdgePadding(maxX, maxY);
    const lastFrameTime = lastFrameTimeRef.current ?? time;
    const deltaTime = Math.min(32, Math.max(12, time - lastFrameTime));
    lastFrameTimeRef.current = time;

    // Change direction randomly every 1.5-3 seconds
    if (time - lastDirectionChangeRef.current > 1500 + Math.random() * 1500) {
      velocityRef.current = generateRandomVelocityRef.current(travelScale);
      lastDirectionChangeRef.current = time;
    }

    // Update position based on true frame delta for consistent motion
    const currentX = x.get();
    const currentY = y.get();

    let newX = currentX + velocityRef.current.x * deltaTime;
    let newY = currentY + velocityRef.current.y * deltaTime;

    const minX = padding;
    const maxBoundX = maxX - padding;
    const minY = padding;
    const maxBoundY = maxY - padding;

    const hitLeft = newX <= minX;
    const hitRight = newX >= maxBoundX;
    const hitTop = newY <= minY;
    const hitBottom = newY >= maxBoundY;
    const hitEdge = hitLeft || hitRight || hitTop || hitBottom;

    // Reflect velocity with slight angular jitter to keep rebounds natural,
    // while forcing inward direction to avoid sticky edge collisions.
    if (hitEdge) {
      newX = Math.max(minX + COLLISION_EPSILON, Math.min(maxBoundX - COLLISION_EPSILON, newX));
      newY = Math.max(minY + COLLISION_EPSILON, Math.min(maxBoundY - COLLISION_EPSILON, newY));

      const baseVelocity = velocityRef.current;
      let vx = hitLeft || hitRight ? -baseVelocity.x : baseVelocity.x;
      let vy = hitTop || hitBottom ? -baseVelocity.y : baseVelocity.y;
      const minMagnitude = speed * travelScale * 0.58;
      const baseMagnitude = Math.max(minMagnitude, Math.hypot(vx, vy));

      if (time - lastCollisionTimeRef.current >= COLLISION_COOLDOWN_MS) {
        const jitter = (Math.random() - 0.5) * (Math.PI / 4.8);
        const angle = Math.atan2(vy, vx) + jitter;
        vx = Math.cos(angle) * baseMagnitude;
        vy = Math.sin(angle) * baseMagnitude;
        lastCollisionTimeRef.current = time;
      }

      if (hitLeft) vx = Math.abs(vx);
      if (hitRight) vx = -Math.abs(vx);
      if (hitTop) vy = Math.abs(vy);
      if (hitBottom) vy = -Math.abs(vy);

      const currentMagnitude = Math.hypot(vx, vy);
      if (currentMagnitude < minMagnitude) {
        const scale = minMagnitude / Math.max(currentMagnitude, 0.0001);
        vx *= scale;
        vy *= scale;
      }

      velocityRef.current = { x: vx, y: vy };
      lastDirectionChangeRef.current = time;
    }

    x.set(newX);
    y.set(newY);
  });

  return (
    <div
      ref={containerRef}
      className={cn(
        "group relative overflow-hidden rounded-2xl bg-neutral-200 p-2 backdrop-blur-sm dark:bg-neutral-800",
        "shadow-[0px_0.5px_1px_0px_var(--color-neutral-400)_inset,0px_1px_0px_0px_var(--color-neutral-100)]",
        "dark:shadow-[0px_1px_0px_0px_var(--color-neutral-950)_inset,0px_1px_0px_0px_var(--color-neutral-800)]",
        backdropBlur &&
          "after:absolute after:inset-0 after:h-full after:w-full after:backdrop-blur-lg after:content-['']",
        containerClassName,
      )}
      style={
        {
          "--noise-opacity": noiseIntensity,
        } as React.CSSProperties
      }
    >
      {/* Moving gradient layers */}
      <GradientLayer
        springX={springX}
        springY={springY}
        gradientColor={gradientColors[0]}
        opacity={0.32}
        multiplier={1}
      />
      <GradientLayer
        springX={springX}
        springY={springY}
        gradientColor={gradientColors[1]}
        opacity={0.24}
        multiplier={0.7}
      />
      <GradientLayer
        springX={springX}
        springY={springY}
        gradientColor={gradientColors[2] || gradientColors[0]}
        opacity={0.18}
        multiplier={1.2}
      />

      {/* Top gradient strip */}
      <motion.div
        className="absolute inset-x-0 top-0 h-1 rounded-t-2xl opacity-65 blur-sm"
        style={{
          background: `linear-gradient(to right, ${gradientColors.join(", ")})`,
          x: animating ? topGradientX : 0,
        }}
      />

      {/* Static Noise Pattern */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <img
          src="https://assets.aceternity.com/noise.webp"
          alt=""
          className="h-full w-full object-cover opacity-[var(--noise-opacity)]"
          style={{ mixBlendMode: "soft-light", filter: "contrast(0.8) saturate(0.7)" }}
        />
      </div>

      {/* Content */}
      <div className={cn("relative z-10", className)}>{children}</div>
    </div>
  );
};
