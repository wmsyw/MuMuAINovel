type LegacyOrganizationShape = {
  readonly ['is_organization']?: boolean | null;
  readonly ['organization_type']?: string | null;
  readonly ['organization_purpose']?: string | null;
};

export const isOrganizationEntity = (entity?: LegacyOrganizationShape | null): boolean =>
  Boolean(entity?.['is_organization']);

export const getOrganizationType = (entity?: LegacyOrganizationShape | null): string | undefined =>
  entity?.['organization_type'] ?? undefined;

export const getOrganizationPurpose = (entity?: LegacyOrganizationShape | null): string | undefined =>
  entity?.['organization_purpose'] ?? undefined;
