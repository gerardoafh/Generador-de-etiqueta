const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch();
  const page = await browser.newPage();
  
  page.on('console', msg => console.log('BROWSER CONSOLE:', msg.text()));

  await page.goto('http://localhost:5173');
  await page.waitForSelector('text/Cola de Impresión');
  
  console.log('Haciendo clic en "Cola de Impresión"...');
  const cards = await page.$$('.grid > div');
  for (const card of cards) {
    const text = await page.evaluate(el => el.textContent, card);
    if (text.includes('Cola de Impresión')) {
      await card.click();
      break;
    }
  }
  
  await new Promise(resolve => setTimeout(resolve, 2000));
  
  console.log('CURRENT URL:', page.url());
  const html = await page.evaluate(() => document.body.innerHTML);
  if (html.includes('Volver al Menú')) {
    console.log('ESTAMOS EN LA COLA DE IMPRESIÓN.');
  } else if (html.includes('Módulos del Sistema')) {
    console.log('ESTAMOS EN EL MENÚ PRINCIPAL.');
  } else {
    console.log('ESTAMOS EN OTRA PÁGINA.');
  }
  
  await browser.close();
})();
