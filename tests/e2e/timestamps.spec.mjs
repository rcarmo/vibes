import {test,expect} from '@playwright/test';
import {verifyTimestampUi} from './helpers/timestamp-fixture.mjs';
for(const timezoneId of ['Europe/Lisbon','UTC','America/New_York']) {
    test.describe(timezoneId,()=>{
        test.use({timezoneId});
        test('SQLite UTC messages show correct relative age and advance',async({page})=>{
            await verifyTimestampUi(page,expect);
        });
    });
}
