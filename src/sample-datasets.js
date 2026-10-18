// One catalog drives sample labels and automatic business selection.
// Keep older samples available without overwriting their original contents.
import catalog from '../data/sample_catalog.json';
export const SAMPLE_DATASETS = [
  ...catalog,
  {filename:'Restaurant_Synthetic.csv', business:'Restaurant', label:'Original restaurant sample', legacy:true},
  {filename:'Furniture_Shop_Synthetic.csv', business:'Furniture shop', label:'Original furniture sample', legacy:true},
  {filename:'Retail_Store_Synthetic.csv', business:'Retail store', label:'Original retail sample', legacy:true},
  {filename:'Cafe.csv', business:'Cafe', label:'Original café dataset', legacy:true},
];
