export declare const MAX_TRAJECTORY_POINTS: number;
export declare const MAX_FILE_BYTES: number;
export declare const MAX_MODEL_FILE_BYTES: number;
export declare const MAX_MISSION_MODEL_BYTES: number;

export interface VignetteValidationOptions {
  knownModelFiles?: Set<string>;
  modelFileSizes?: Map<string, number>;
  localeKeySets?: Map<string, Set<string>>;
}

export declare function validateMissionSpec(
  data: unknown,
  options?: { fileName?: string } & VignetteValidationOptions,
): string[];

export declare function validateMissionFileText(
  text: string,
  options?: { fileName?: string } & VignetteValidationOptions,
): { errors: string[]; data: unknown };

export declare function validateIndexSpec(
  data: unknown,
  options?: { knownSlugs?: Set<string> },
): string[];
