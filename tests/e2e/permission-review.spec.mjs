import {test,expect} from '@playwright/test';
import {mountPermissionReview,verifyPermissionLayout} from './helpers/permission-review-fixture.mjs';
for(const colorScheme of ['light','dark']) for(const viewport of [{width:1280,height:900},{width:390,height:844},{width:320,height:568},{width:844,height:390}]) {
    test.describe(`${colorScheme} ${viewport.width}x${viewport.height}`,()=>{
        test.use({viewport,colorScheme});
        test('permission commands wrap exactly with copy and fixed actions',async({page})=>{
            await mountPermissionReview(page);
            await verifyPermissionLayout(page,expect);
        });
    });
}
