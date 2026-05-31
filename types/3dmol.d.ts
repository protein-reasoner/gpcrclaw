declare module "3dmol" {
  type Viewer = {
    addModel(data: string, format: string): void;
    clear(): void;
    render(): void;
    setStyle(selection: object, style: object): void;
    zoomTo(): void;
  };

  const mol3d: {
    createViewer(element: HTMLElement | null, options?: object): Viewer;
  };

  export default mol3d;
}
