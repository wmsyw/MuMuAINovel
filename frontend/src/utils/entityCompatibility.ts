export const LEGACY_ORGANIZATION_FIELDS = {
  flag: 'is_organization',
  type: 'organization_type',
  purpose: 'organization_purpose',
} as const;

type LegacyOrganizationTextFields = {
  readonly [LEGACY_ORGANIZATION_FIELDS.type]?: string | null;
  readonly [LEGACY_ORGANIZATION_FIELDS.purpose]?: string | null;
};

export type LegacyOrganizationEntityFields = LegacyOrganizationTextFields & {
  readonly [LEGACY_ORGANIZATION_FIELDS.flag]?: boolean | null;
};

export type LegacyOrganizationCharacterFields = LegacyOrganizationTextFields & {
  readonly [LEGACY_ORGANIZATION_FIELDS.flag]: boolean;
};

export type LegacyOrganizationPayloadFields = {
  [LEGACY_ORGANIZATION_FIELDS.flag]?: boolean;
  [LEGACY_ORGANIZATION_FIELDS.type]?: string;
  [LEGACY_ORGANIZATION_FIELDS.purpose]?: string;
};

export type LegacyOrganizationFormValues = LegacyOrganizationPayloadFields & {
  organization_members?: string;
};

export const isOrganizationEntity = (entity?: LegacyOrganizationEntityFields | null): boolean =>
  Boolean(entity?.[LEGACY_ORGANIZATION_FIELDS.flag]);

export const getOrganizationType = (entity?: LegacyOrganizationEntityFields | null): string | undefined =>
  entity?.[LEGACY_ORGANIZATION_FIELDS.type] ?? undefined;

export const getOrganizationPurpose = (entity?: LegacyOrganizationEntityFields | null): string | undefined =>
  entity?.[LEGACY_ORGANIZATION_FIELDS.purpose] ?? undefined;

export const buildLegacyOrganizationFlag = (isOrganization: boolean): LegacyOrganizationPayloadFields => ({
  [LEGACY_ORGANIZATION_FIELDS.flag]: isOrganization,
});

export const buildLegacyOrganizationCreateFields = (
  values: LegacyOrganizationFormValues,
): LegacyOrganizationPayloadFields => ({
  ...buildLegacyOrganizationFlag(true),
  [LEGACY_ORGANIZATION_FIELDS.type]: getOrganizationType(values),
  [LEGACY_ORGANIZATION_FIELDS.purpose]: getOrganizationPurpose(values),
});
