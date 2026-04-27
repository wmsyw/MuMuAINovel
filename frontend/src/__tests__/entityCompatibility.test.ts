import { describe, expect, it } from 'vitest';

import {
  LEGACY_ORGANIZATION_FIELDS,
  buildLegacyOrganizationCreateFields,
  buildLegacyOrganizationFlag,
  getOrganizationPurpose,
  getOrganizationType,
  isOrganizationEntity,
} from '../utils/entityCompatibility';

describe('entity compatibility helpers', () => {
  it('builds legacy organization payload fields through the centralized adapter', () => {
    const formValues = {
      [LEGACY_ORGANIZATION_FIELDS.type]: '守卫组织',
      [LEGACY_ORGANIZATION_FIELDS.purpose]: '维护夜禁秩序',
    };

    const payload = buildLegacyOrganizationCreateFields(formValues);

    expect(payload[LEGACY_ORGANIZATION_FIELDS.flag]).toBe(true);
    expect(payload[LEGACY_ORGANIZATION_FIELDS.type]).toBe('守卫组织');
    expect(payload[LEGACY_ORGANIZATION_FIELDS.purpose]).toBe('维护夜禁秩序');
    expect(isOrganizationEntity(payload)).toBe(true);
    expect(getOrganizationType(payload)).toBe('守卫组织');
    expect(getOrganizationPurpose(payload)).toBe('维护夜禁秩序');
  });

  it('builds character and organization flags without page-local field ownership', () => {
    expect(buildLegacyOrganizationFlag(false)[LEGACY_ORGANIZATION_FIELDS.flag]).toBe(false);
    expect(buildLegacyOrganizationFlag(true)[LEGACY_ORGANIZATION_FIELDS.flag]).toBe(true);
  });
});
