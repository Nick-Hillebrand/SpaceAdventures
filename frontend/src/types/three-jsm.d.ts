// P36: three ships no bundled TypeScript types in this resolution, and its
// examples/jsm addons (GLTFLoader, OrbitControls) have no @types package —
// declare loosely, same convention as globe.d.ts (P13).
declare module 'three';
declare module 'three/examples/jsm/loaders/GLTFLoader.js';
declare module 'three/examples/jsm/controls/OrbitControls.js';
