package ru.gr1zle.lepka_platform;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.provider.DocumentsContract;
import android.provider.MediaStore;
import android.util.Base64;
import androidx.core.content.FileProvider;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;
import org.json.JSONObject;
import io.flutter.plugin.common.MethodChannel;
import io.flutter.plugin.common.PluginRegistry;

/** UI operations retain their MethodChannel result while normal platform calls continue. */
public final class MediaActions implements PluginRegistry.ActivityResultListener {
    private final Context context;
    private Activity activity;
    private volatile MethodChannel.Result pending;
    private byte[] bytes;
    private File cameraFile;
    private String fileName;
    private static final int SAVE=2801,CAMERA=2802;
    public MediaActions(Context context) { this.context=context; }
    public void attach(Activity activity) { this.activity=activity; }
    public void detach(boolean permanent) {
        activity=null;
        if(permanent && pending!=null) finish(null,"Операция прервана");
    }
    private synchronized void finish(String value,String error) {
        MethodChannel.Result result=pending;bytes=null;
        if(cameraFile!=null) { cameraFile.delete();cameraFile=null; }
        pending=null;
        if(result!=null) {
            if(error==null)result.success(value);else result.error("media_unavailable",error,null);
        }
    }
    public void begin(String operation,String value,MethodChannel.Result result) {
        if(pending!=null) { result.error("media_busy","Завершите предыдущую операцию",null);return; }
        if(activity==null) { result.error("no_activity","Android-окно недоступно",null);return; }
        pending=result;
        try {
            Intent intent;
            if(operation.equals("fileSave")) {
                JSONObject input=new JSONObject(value);fileName=input.getString("name");
                String mime=input.getString("mime");
                if(fileName.length()>120 || fileName.contains("/") || fileName.contains("\\") ||
                   !(mime.equals("image/png") || mime.equals("application/pdf") || mime.equals("application/json")))throw new IllegalArgumentException();
                String encoded=input.getString("base64");
                int maxBytes=(mime.equals("application/json")?20:10)*1024*1024;
                if(encoded.length()>((maxBytes+2)/3)*4)throw new IllegalArgumentException();
                bytes=Base64.decode(encoded,Base64.DEFAULT);
                if(bytes.length==0 || bytes.length>maxBytes)throw new IllegalArgumentException();
                intent=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                    .setType(mime).putExtra(Intent.EXTRA_TITLE,fileName);
                activity.startActivityForResult(intent,SAVE);
            } else if(operation.equals("cameraCapture")) {
                cameraFile=File.createTempFile("lepka-camera-",".jpg",context.getCacheDir());
                Uri uri=FileProvider.getUriForFile(context,context.getPackageName()+".lepka.files",cameraFile);
                intent=new Intent(MediaStore.ACTION_IMAGE_CAPTURE).putExtra(MediaStore.EXTRA_OUTPUT,uri)
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                intent.setClipData(android.content.ClipData.newRawUri("Снимок",uri));
                activity.startActivityForResult(intent,CAMERA);
            } else throw new IllegalArgumentException();
        } catch(Exception failure) { finish(null,"Не удалось открыть выбор файла или камеру"); }
    }
    @Override public boolean onActivityResult(int requestCode,int resultCode,Intent data) {
        if(requestCode!=SAVE && requestCode!=CAMERA)return false;
        if(pending==null)return true;
        if(resultCode!=Activity.RESULT_OK) { finish("{\"cancelled\":true}",null);return true; }
        new Thread(() -> complete(requestCode,data),"LepkaMedia").start();
        return true;
    }
    private void complete(int requestCode,Intent data) {
        Uri destination=null;
        try {
            if(requestCode==SAVE) {
                destination=data==null?null:data.getData();
                if(destination==null)throw new IllegalArgumentException();
                try(OutputStream output=context.getContentResolver().openOutputStream(destination,"wt")) {
                    if(output==null)throw new IllegalStateException();
                    output.write(bytes);output.flush();
                }
                // Some providers report success before writing. Read back and verify the actual bytes.
                MessageDigest digest=MessageDigest.getInstance("SHA-256");long count=0;
                try(InputStream input=context.getContentResolver().openInputStream(destination)) {
                    if(input==null)throw new IllegalStateException();
                    byte[] buffer=new byte[8192];int size;
                    while((size=input.read(buffer))!=-1) { count+=size;if(count>bytes.length)throw new IllegalStateException();digest.update(buffer,0,size); }
                }
                if(count!=bytes.length || !java.util.Arrays.equals(digest.digest(),MessageDigest.getInstance("SHA-256").digest(bytes)))throw new IllegalStateException();
                finish(new JSONObject().put("cancelled",false).put("bytes",count).put("name",fileName).toString(),null);
            } else {
                BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;
                BitmapFactory.decodeFile(cameraFile.getAbsolutePath(),options);
                if(options.outWidth<=0 || options.outHeight<=0)throw new IllegalArgumentException();
                options.inSampleSize=1;
                while(options.outWidth/options.inSampleSize>1600 || options.outHeight/options.inSampleSize>1600)options.inSampleSize*=2;
                options.inJustDecodeBounds=false;
                Bitmap bitmap=BitmapFactory.decodeFile(cameraFile.getAbsolutePath(),options);
                if(bitmap==null)throw new IllegalArgumentException();
                // Rotation is applied before stripping EXIF from the normalised JPEG.
                android.media.ExifInterface exif=new android.media.ExifInterface(cameraFile.getAbsolutePath());
                int orientation=exif.getAttributeInt(android.media.ExifInterface.TAG_ORIENTATION,1);
                android.graphics.Matrix matrix=new android.graphics.Matrix();
                if(orientation==3)matrix.postRotate(180);else if(orientation==6)matrix.postRotate(90);else if(orientation==8)matrix.postRotate(270);
                if(!matrix.isIdentity()) { Bitmap rotated=Bitmap.createBitmap(bitmap,0,0,bitmap.getWidth(),bitmap.getHeight(),matrix,true);if(rotated!=bitmap)bitmap.recycle();bitmap=rotated; }
                ByteArrayOutputStream output=new ByteArrayOutputStream();bitmap.compress(Bitmap.CompressFormat.JPEG,90,output);bitmap.recycle();
                byte[] photo=output.toByteArray();if(photo.length>5*1024*1024)throw new IllegalArgumentException();
                finish(new JSONObject().put("cancelled",false).put("imageBase64",Base64.encodeToString(photo,Base64.NO_WRAP)).toString(),null);
            }
        } catch(Exception failure) {
            if(destination!=null)try { DocumentsContract.deleteDocument(context.getContentResolver(),destination); }catch(Exception ignored) { }
            finish(null,"Не удалось записать или проверить файл. Выберите другую папку");
        }
    }
}
