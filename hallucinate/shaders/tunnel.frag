#version 440
#include "common.glsl"

// A warp tunnel of neon grid, flying forward: the rings rush past faster with the music, each spoke of the grid
// lights up with its part of the spectrum, the walls twist and melt a little as if seen through a fever, and a
// beat sends a flash down the tunnel.
void main() {
    vec3 a = vivid(c0), b = vivid(c1), c = vivid(c2);
    vec2 p = aspectUv();
    // a slow sway of the vanishing point, and a dreamlike melt of the walls
    p += 0.06 * vec2(sin(time * 0.23), cos(time * 0.31));
    float r = max(length(p), 0.001);
    float ang = atan(p.y, p.x);
    float melt = fbm(vec2(ang * 1.5, time * 0.15)) - 0.5;
    float depth = 0.35 / r + time * (0.9 + 1.6 * energy) + melt * 0.6 * (0.5 + mid);
    float twist = ang / 6.2831853 + 0.05 * sin(depth * 0.5) + 0.08 * time;
    // the grid: rings along the depth, spokes around
    float ring = abs(fract(depth) - 0.5);
    float spoke = abs(fract(twist * 16.0) - 0.5);
    float rings = exp(-ring * 26.0);
    float spokes = exp(-spoke * 30.0);
    // each spoke follows its band of the spectrum, mirrored left to right
    float side = abs(ang) / 3.14159265;
    float level = band(side * 0.95 + 0.02);
    float fog = smoothstep(0.0, 0.45, r);                 // the far end fades into the dark
    vec3 tint = mix(a, b, 0.5 + 0.5 * sin(depth * 0.7 + twist * 6.2831853));
    vec3 col = vec3(0.0);
    col += tint * rings * (1.0 + 0.8 * bass + 0.6 * beat) * fog;  // (lit even when quiet)
    col += mix(b, c, side) * spokes * (0.5 + 1.2 * level) * fog;
    // a hot core at the vanishing point, and the flash of a beat running down the walls
    col += mix(c, a, 0.5) * exp(-r * 9.0) * (0.4 + 0.5 * treble);
    float flash = exp(-abs(fract(depth * 0.25 - time * 0.4) - 0.5) * 14.0) * beat;
    col += a * flash * 0.5 * fog;
    // faint stars between the lines
    col += stars(qt_TexCoord0 * res, 9.0, 0.04, 0.6) * 0.35 * (1.0 - rings) * fog;
    fragColor = vec4(finish(col), 1.0) * qt_Opacity;
}
