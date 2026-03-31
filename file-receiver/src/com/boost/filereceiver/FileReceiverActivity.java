package com.boost.filereceiver;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * Minimal activity that receives shared files and saves them to
 * /sdcard/Download/wa_exports/. Appears in the Android share sheet
 * as "Salvar Arquivo". Finishes immediately after saving.
 */
public class FileReceiverActivity extends Activity {

    private static final String EXPORT_DIR = "wa_exports";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        Intent intent = getIntent();
        String action = intent.getAction();

        if (Intent.ACTION_SEND.equals(action)) {
            Uri uri = intent.getParcelableExtra(Intent.EXTRA_STREAM);

            if (uri != null) {
                saveFile(uri);
            } else {
                // Some apps send text directly instead of a file URI
                String text = intent.getStringExtra(Intent.EXTRA_TEXT);
                if (text != null) {
                    saveText(text);
                } else {
                    Toast.makeText(this, "Nenhum arquivo recebido", Toast.LENGTH_SHORT).show();
                }
            }
        }

        finish();
    }

    private void saveFile(Uri uri) {
        try {
            File dir = new File(
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
                EXPORT_DIR
            );
            dir.mkdirs();

            // Build filename from URI or use timestamp
            String name = getFileName(uri);
            if (name == null || name.isEmpty()) {
                name = "export_" + System.currentTimeMillis() + ".txt";
            }

            File outFile = new File(dir, name);

            InputStream in = getContentResolver().openInputStream(uri);
            if (in == null) {
                Toast.makeText(this, "Erro ao ler arquivo", Toast.LENGTH_SHORT).show();
                return;
            }

            OutputStream out = new FileOutputStream(outFile);
            byte[] buf = new byte[8192];
            int len;
            while ((len = in.read(buf)) > 0) {
                out.write(buf, 0, len);
            }
            out.close();
            in.close();

            Toast.makeText(this, "Salvo: " + outFile.getName(), Toast.LENGTH_SHORT).show();

        } catch (Exception e) {
            Toast.makeText(this, "Erro: " + e.getMessage(), Toast.LENGTH_SHORT).show();
        }
    }

    private void saveText(String text) {
        try {
            File dir = new File(
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
                EXPORT_DIR
            );
            dir.mkdirs();

            String name = "export_" + System.currentTimeMillis() + ".txt";
            File outFile = new File(dir, name);

            FileOutputStream out = new FileOutputStream(outFile);
            out.write(text.getBytes("UTF-8"));
            out.close();

            Toast.makeText(this, "Salvo: " + outFile.getName(), Toast.LENGTH_SHORT).show();

        } catch (Exception e) {
            Toast.makeText(this, "Erro: " + e.getMessage(), Toast.LENGTH_SHORT).show();
        }
    }

    private String getFileName(Uri uri) {
        // Try to get display name from content resolver
        try {
            android.database.Cursor cursor = getContentResolver().query(
                uri, null, null, null, null
            );
            if (cursor != null && cursor.moveToFirst()) {
                int idx = cursor.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME);
                if (idx >= 0) {
                    String name = cursor.getString(idx);
                    cursor.close();
                    return name;
                }
                cursor.close();
            }
        } catch (Exception ignored) {}

        // Fallback: use last path segment
        String path = uri.getLastPathSegment();
        if (path != null) {
            return path.replaceAll("[^a-zA-Z0-9._\\- ]", "_");
        }
        return null;
    }
}
