export declare const MAX_TRAJECTORY_POINTS: number;
export declare const MAX_FILE_BYTES: number;

export declare function validateMissionSpec(
  data: unknown,
  options?: { fileName?: string },
): string[];

export declare function validateMissionFileText(
  text: string,
  options?: { fileName?: string },
): { errors: string[]; data: unknown };

export declare function validateIndexSpec(
  data: unknown,
  options?: { knownSlugs?: Set<string> },
): string[];
